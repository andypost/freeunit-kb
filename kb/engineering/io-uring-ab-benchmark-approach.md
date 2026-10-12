# A/B Benchmark Approach — io_uring Event Engine (PRs #30–#32)

**Repo:** `andypost/unit`
**Author:** Andrey Postnikov (andypost), co-authored with Claude Code (Claude Fable 5)
**Date:** 2026-07-12
**PRs:** [#30](https://github.com/andypost/unit/pull/30) (Stage 1), [#31](https://github.com/andypost/unit/pull/31) (Stage 2), [#32](https://github.com/andypost/unit/pull/32) (harness)

---

## TL;DR

Three PRs deliver: (1) an opt-in `io_uring` event engine for Nginx Unit, (2) a
completion-mode accept path with feature-tiered runtime probing, and (3) a
**build-agnostic A/B benchmark harness** that makes performance comparisons
between engine implementations cheap, rigorous, and reproducible. The harness
is the enabler — it let Andrey iterate through 4 architectural pivots in
~24 hours, each backed by hard numbers.

---

## PR #30 — Stage 1: Poll-Mode Readiness Bridge

**Goal:** Use io_uring as a "better epoll" — a multishot `IORING_OP_POLL_ADD`
per armed direction feeds Unit's existing `read_ready`/`write_ready` latches.
All `recv`/`send`/`accept` syscalls stay in userspace.

**Key design decisions:**
- **user_data encoding**: `{slot_index, 14-bit generation, direction}` packed
  into 64-bit CQE `user_data` — enables stale-CQE rejection after fd reuse.
- **Edge-like delivery handling**: multishot poll is edge-like (one CQE per
  wait-queue wakeup, never re-reports a still-ready fd). The engine ships
  `nxt_io_uring_conn_io` with a recvbuf EOF shim, set-only EOF/error latches,
  and a per-drain sequence dedupe — each fixing a real bug found during bring-up.
- **Graceful fallback**: runtime probe (functional multishot-poll test, not
  version parsing) + `NXT_IO_URING=0` kill-switch. `create()` failure at any
  point degrades to epoll instead of dying.
- **Build flags**: `--io-uring` (opt-in, epoll stays default) and
  `--io-uring-default` (io_uring first). Two build flavours = clean A/B pair.

**Bugs found during bring-up (all fixed):**
1. **Pending-EOF loss** (proxy stall): response + FIN in one wakeup → single
   POLLIN|POLLRDHUP CQE → recv consumes data → EOF never re-reported.
2. **Double handler dispatch** (router SIGSEGV): one CQ drain holds several
   CQEs for same fd → both dispatched read handler → use-after-free.
3. **Non-monotonic CQE masks** erasing the EOF latch within a single drain.
4. **Engine-create fallback** only in main process, not children → ring
   exhaustion in a child killed it.

---

## PR #31 — Stage 2: Completion-Mode Accept, Feature Tiers, Hardening

**Goal:** Move from poll-mode to completion-mode for accept; add per-feature
runtime probing; review hardening pass.

**Architecture pivots driven by benchmarks:**

| Pivot | What was tried | What benchmarks showed | Resolution |
|-------|---------------|----------------------|------------|
| **Multishot accept** | `IORING_ACCEPT_MULTISHOT` — persistent wake-one registration | **Worker starvation**: kernel funnels all connections to first-armed ring; 7/8 workers idle; throughput at single-worker ceiling | Replaced with **oneshot accept re-armed per completion** — each ring keeps ≤1 pending accept, kernel distributes like N threads in `accept(2)` |
| **Stay-armed-while-BLOCKED** | Stage 1 disarmed (POLL_REMOVE) on BLOCKED + re-armed (POLL_ADD) on next enable = ~1 SQE pair/request | Contributed to keepalive CPU regression (+18.7% ab ka_hi) | **Keep multishot armed**, latch readiness only → enable is zero-SQE |
| **SINGLE_ISSUER + DEFER_TASKRUN** | Kernel-side submitter binding for lower overhead | Kernel binds submitter at `io_uring_setup()` time; Unit creates engine on router-main thread, polls on worker thread → `-EEXIST` busy-loop on every worker | **Dropped entirely** — documented as future work if ring creation moves to polling thread |
| **RECV tier (buf_ring multishot recv)** | Remove per-read `recv(2)` + one copy | Three coupled constraints not yet solved (scope, buffer lifetime, read discipline) → risk of soak signal-11 | **Deliberately deferred** — capability detected, tier clamped to ACCEPT |

**Feature tiers (runtime-probed, never version-parsed):**
```
POLL   ← floor: multishot POLL_ADD (kernel ≥5.13)
ACCEPT ← oneshot IORING_OP_ACCEPT (kernel ≥5.19)
RECV   ← buf_ring + multishot recv (kernel ≥6.0) — deferred
OPT    ← SINGLE_ISSUER + DEFER_TASKRUN — dropped
```
`NXT_IO_URING_FORCE_TIER=none|create|poll|accept|recv|opt` exercises every
degraded path on a modern kernel.

**Review hardening (5 verified bugs):**
1. Generation-wrap fd death (13-bit gen compared against raw uint16_t)
2. Ring fd + mmap leak on failed create
3. Duplicate user_data registrations from oneshot re-arm
4. Zeroed client address after peer RST (getpeername result discarded)
5. Negative-fd table corruption

---

## PR #32 — A/B Benchmark Harness (the key enabler)

### Design philosophy

> "Very convenient to collect numbers with Claude — now testing performance of
> different variants is not a big pain anymore."
> — Adapted from A. Dubovskoy's remark about a similar workflow

The harness (`tools/bench-engines.sh` + `tools/bench-engines-report.py`) is
designed around a single principle: **make the cost of running a rigorous A/B
comparison approach zero**, so you iterate on architecture, not on test setup.

### How it works

```
┌──────────────────────────────────────────────────────┐
│             tools/bench-engines.sh                     │
│                                                       │
│  Input: two unitd build directories (A and B)         │
│  Output: markdown summary with mean±stdev + delta%    │
│                                                       │
│  ┌─────────────┐    ┌─────────────┐                  │
│  │  Build A    │    │  Build B    │                  │
│  │  (epoll)    │    │  (io_uring) │                  │
│  └──────┬──────┘    └──────┬──────┘                  │
│         │    interleaved    │                         │
│         └────────┬─────────┘                         │
│                  ▼                                     │
│         ┌────────────────┐                           │
│         │ Scenario Matrix │                           │
│         │ (5 scenarios)   │                           │
│         └───────┬────────┘                           │
│                 ▼                                     │
│  ┌──────────────────────────────────┐                │
│  │  oha (JSON, primary) + ab (secondary) │           │
│  └──────────────┬───────────────────┘                │
│                 ▼                                     │
│  ┌──────────────────────────────────┐                │
│  │  bench-engines-report.py          │                │
│  │  → markdown tables per scenario   │                │
│  │  → mean ± stdev over N rounds     │                │
│  │  → B-vs-A delta %                 │                │
│  └──────────────────────────────────┘                │
└──────────────────────────────────────────────────────┘
```

### Rigor features

| Feature | Purpose |
|---------|---------|
| **Interleaved A/B rounds** | Cancels thermal/cache drift; 5 rounds by default |
| **Null A/A drift test** | Point both slots at same build → establishes noise floor before any A/B claim. oha RPS ±5-8%, ab RPS ±1.5%, CPU µs/req ±1% |
| **Engine identity assertion** | Greps `using "<name>" event engine` log line; aborts on accidental A/A unless `--allow-same` |
| **Per-round isolation** | Isolated statedir/control socket/log per build per round |
| **CPU pinning** | Server tree pinned at spawn (taskset); load generator on separate cores |
| **Two load tools** | oha (JSON, primary) + ApacheBench (tight metric, secondary) — cross-validation |
| **Scenario matrix** | 5 scenarios designed to expose different bottlenecks |

### Scenario matrix

| Scenario | Config | What it exposes |
|----------|--------|-----------------|
| `ret200_ka_hi` | return-200, keepalive, c=256 | Steady-state throughput, high concurrency |
| `ret200_ka_lo` | return-200, keepalive, c=8 | **Listener wake-distribution effects** (thundering herd detector) |
| `ret200_close` | Connection: close, c=16 | **Accept-path cost** — connections created/destroyed per request |
| `proxy_ka` | proxy→self, keepalive, c=64 | Internal peer connection accept churn |
| `php_ka` | PHP hello app, keepalive, c=8 | **Process-tree CPU** — real-world app server cost |

### Metrics collected per scenario per round

- **RPS** (requests/sec)
- **p50 latency**
- **p99 latency**
- **Error count** (non-2xx, timeouts, connection errors)
- **Router CPU µs/request** (the tightest metric — A/A noise ~±1%)

### What the benchmarks revealed (the value)

The harness was the tool that made the architectural pivots possible. Each
pivot was a **hypothesis → measurement → decision** cycle:

1. **Stage 1 vs epoll**: Throughput parity, but CPU +4-50% on accept-heavy
   paths. → Hypothesis: thundering herd from multishot POLL_ADD (no
   EPOLLEXCLUSIVE analogue). → **Confirmed by `ka_lo` and `close` scenarios**.

2. **Stage 2 multishot accept**: Looked like a CPU win (-8..-32%), but
   throughput at single-worker ceiling. → Hypothesis: worker starvation.
   → **Confirmed by per-thread accept accounting** (32/32 connections to one ring).
   → Fixed with oneshot accept (11-14% distribution across all 8 workers).

3. **Stay-armed-while-BLOCKED**: CPU regression on keepalive dropped from
   +18.7% to +3.8% (ab ka_hi). → **Measured improvement, not speculation**.

4. **SINGLE_ISSUER**: Enabled → every worker busy-loops on -EEXIST. →
   **Caught immediately** by the harness, not in production.

### Results summary

**Stage 2 net standing: parity-minus.** No scenario shows an io_uring win on
this workload set. The projected wins were always in the deferred RECV tier
(buffer-ring multishot recv: removes per-read `recv(2)` + one copy).

| Scenario | Δ throughput (ab) | Δ CPU (ab) | Verdict |
|----------|-------------------|------------|---------|
| ret200_ka_hi | +0.6% | +3.8% | parity |
| ret200_ka_lo | -1.0% | +15.5% | parity-ish |
| ret200_close | -1.5% | +12.5% | slight CPU cost |
| php_ka | -0.3% | +13.8% | parity |
| proxy_ka | **-8.7%** | **+11.3%** | real regression (accept re-arm) |

---

## Connection to A. Dubovskoy's approach

Andrey's friend Alexey Dubovskoy ([adubovskoy/tbook_converter#2](https://github.com/adubovskoy/tbook_converter/issues/2))
shares a similar philosophy: using Claude (AI agent) to **automate the collection
and comparison of performance numbers** across variants, making it "not a big
pain anymore" to test different implementations.

The io_uring A/B harness embodies the same principle at a systems level:
- **Variant creation is cheap** (two build dirs, one flag)
- **Measurement is automated** (interleaved rounds, noise floor, scenario matrix)
- **Comparison is rigorous** (mean ± stdev, delta %, verdict vs noise)
- **Iteration is fast** (the entire Stage 1→2 journey took ~24 hours, with 4
  architectural pivots each backed by hard data)

The key insight: **when the cost of measuring drops to near-zero, you make
decisions on data, not on intuition.** The multishot-accept starvation was not
caught by reasoning or code review — it was caught by the benchmark showing
single-worker throughput. The stay-armed fix was validated not by reading code
but by seeing +18.7% → +3.8% in the CPU column.

---

## Kernel version matrix — how io_uring evolved 5.x → 7.x

io_uring changed radically across kernel versions. Each tier in the engine maps
to a specific kernel feature generation:

| Kernel | Feature | Engine tier | Impact |
|--------|---------|-------------|--------|
| 5.1 (2019) | `io_uring` base (SQ/CQ rings) | — | Foundation |
| 5.5 (2020) | `IORING_FEAT_NODROP` | Floor | CQ doesn't drop completions on overflow — queues in backlog |
| 5.11 (2021) | `IORING_FEAT_EXT_ARG` | Floor | `io_uring_enter` with native timeout — no separate timerfd |
| 5.13 (2021) | Multishot `POLL_ADD` stable | **POLL (floor)** | One `POLL_ADD` per fd/direction, kernel sends CQE per wakeup |
| 5.19 (2022) | `IORING_OP_ACCEPT` + buf_ring | **ACCEPT tier** | Completion-mode accept: kernel creates client fd directly |
| 6.0 (2022) | `IORING_RECV_MULTISHOT` + `send_zc` | **RECV tier (deferred)** | Zero-copy recv into ring buffer — removes `recv(2)` + one `memcpy` |
| 6.0+ (2022) | `SINGLE_ISSUER` + `DEFER_TASKRUN` | **OPT tier (dropped)** | Ring bound to one task; Unit's thread model incompatible → busy-loop |
| 7.0 (2024) | Stabilization | Benchmarks | All PR testing done on kernel 7.0 |

**Key architectural decision:** kernel features are **never** detected by version
parsing (`uname`). Each tier is resolved via a **runtime functional probe**:

- POLL: functional multishot-poll test (arm, check for `IORING_CQE_F_MORE`)
- ACCEPT: `io_uring_get_probe_ring()` + `io_uring_opcode_supported()`
- RECV: (probe removed — tier deferred)
- `NXT_IO_URING_FORCE_TIER` simulates any older kernel on 7.0 for testing fallbacks

**Deployment matrix:**

| Environment | Resolved tier | Behaviour |
|-------------|---------------|-----------|
| Kernel ≥7.0 | ACCEPT (max implemented) | Oneshot accept, stay-armed-while-BLOCKED |
| Kernel 5.13–5.18 | POLL | Multishot poll + userspace `accept4()`, thundering herd on accept |
| Kernel <5.13 | Fallback → epoll | io_uring not registered |
| seccomp `SCMP_ACT_KILL` | Fallback → epoll | `NXT_IO_URING=0` kill-switch before any syscall |
| `io_uring_disabled` sysctl | Fallback → epoll | Probe returns NXT_ERROR |

---

## Rust vs C: why the RECV tier is deferred in C but default in Rust

The three constraints that forced the RECV tier's deferral in the C engine (PR #31
§2.4, OQ2, read discipline) are **structural limitations of the C architecture**,
not missing features in io_uring. Rust solves all three through its type system.

> **Note:** Buran (the Rust-based orchestrator benchmarked against FreeUnit) is
> expected to undergo significant changes in the coming days. The comparison
> below reflects the current state; performance characteristics may shift.

### Constraint 1: Scope — data conns vs UDS port sockets

**C (PR #31 §2.4):**
> "recv must cover data conns only, never UDS port sockets (SCM_RIGHTS/cred
> cmsgs). But both arm read through the same `enable_read` and `nxt_fd_event_t`
> has no type tag to separate them — and §1.7 forbids adding one."

**Rust:**
Different connection types are different types. The compiler enforces the
correct path — `PortSocket` can never reach `buf_ring_recv()`:

```rust
enum ConnKind {
    Data(DataConn),     // recv via buf_ring (zero-copy)
    Port(PortSocket),   // recv via recvmsg (ancillary data)
}

match conn.kind {
    ConnKind::Data(c) => buf_ring_recv(c).await,
    ConnKind::Port(c) => recvmsg(c).await,
}
```

No runtime type tag needed. The type itself is the discriminator.

### Constraint 2: Buffer lifetime — ring buffer across app round-trip

**C (PR #31 §OQ2):**
> "The zero-copy win needs a ring buffer handed to the pipeline as `c->read`,
> but the router can pin `c->read` across the app round-trip and starve the
> ring; the safe answer is copy-out at the parse boundary, and a naive
> copy-out-everywhere model adds a userspace copy that makes it net-negative.
> A lifecycle slip is a soak signal-11."

**Rust:**
The borrow checker tracks buffer ownership. `Drop` trait guarantees cleanup:

```rust
struct RingBuffer<'ring> {
    data: &'ring mut [u8],
    id: u16,
    _marker: PhantomData<&'ring ()>,
}

impl Drop for RingBuffer<'_> {
    fn drop(&mut self) {
        // Automatic return to buf_ring when buffer goes out of scope
        return_to_ring(self.id);
    }
}

fn handle_request(buf: RingBuffer<'_>) {
    let owned = Bytes::copy_from_slice(&buf.data);
    drop(buf);  // ring buffer returned here, guaranteed
    send_to_worker(owned).await;
}
```

Cannot forget to return the buffer. Cannot use-after-free. No signal-11 risk.

### Constraint 3: Read discipline — block_read vs multishot recv

**C (PR #31):**
> "Unit `block_read()`s after each read while multishot recv delivers
> continuously, so a blocked conn accumulates ring buffers until ENOBUFS and
> the degrade-to-poll+recv path must be robust."

**Rust:**
Async/await provides natural backpressure — no data is requested until the
previous buffer is consumed:

```rust
async fn read_loop(conn: DataConn) {
    loop {
        let buf = conn.buf_ring_recv().await;
        process(buf).await;  // <-- backpressure: no new recv until done
    }
}
```

### Threading model — the root cause

| | C (Nginx Unit) | Rust (Buran) |
|---|---|---|
| **Architecture** | Router-main creates engine, workers poll | Thread-per-core, each owns its ring |
| **SINGLE_ISSUER** | ✗ (create ≠ poll thread → `-EEXIST`) | ✓ (ring owned by one thread) |
| **DEFER_TASKRUN** | ✗ (same reason) | ✓ (poll on creating thread) |
| **Shared state** | Mutex on router state | None (shared-nothing) |
| **Locks** | Required for cross-worker coordination | Not needed |

```
C (Unit):                          Rust (Buran):
  router-main                      Thread 1 (core 0) ── ring 1 ── conns on core 0
    ├── worker 1 ── epoll          Thread 2 (core 1) ── ring 2 ── conns on core 1
    ├── worker 2 ── epoll          Thread 3 (core 2) ── ring 3 ── conns on core 2
    └── worker 8 ── epoll          ...

  Engine created on main thread,   Each thread creates and polls
  polled on worker thread.          its own ring. SINGLE_ISSUER works.
  SINGLE_ISSUER impossible.
```

### Summary: why Rust wins on io_uring

| Aspect | C (Unit) | Rust (Buran) | Root cause |
|--------|----------|--------------|------------|
| SINGLE_ISSUER | ✗ | ✓ | Thread-per-core |
| Zero-copy recv | Deferred | ✓ default | Ownership tracking via borrow checker |
| Buffer lifetime | Manual pointer (`c->read`) | `Drop` + lifetimes | Compile-time guarantee |
| Backpressure | `block_read()` flag | async/await | No manual sync |
| Scope (data vs UDS) | No type tag in `nxt_fd_event_t` | Enum/match | Type-level safety |
| send_zc | Not implemented | Likely implemented | Refcounted `Arc<Bytes>` |
| Locks | Mutex on shared state | None | Shared-nothing |

**Bottom line:** The RECV tier in C is a "follow-up PR with three hard
constraints." In Rust, it's the default path — zero-copy recv, send_zc, and
SINGLE_ISSUER all work out of the box because the type system and ownership
model handle what C requires manually. This is the structural reason Buran
achieves ~265k RPS vs FreeUnit's ~141k RPS at C10K.

> ⚠️ **Buran is expected to change significantly in the coming days.**
> Performance numbers and architectural details may shift. Re-benchmark
> after the update.

---

## Files

| File | PR | Description |
|------|-----|-------------|
| `src/nxt_io_uring_engine.c` | #30, #31 | The engine implementation (2085 lines) |
| `src/nxt_event_engine.c` | #30, #31 | Fallback logic, engine selection |
| `src/nxt_event_engine.h` | #30, #31 | Engine contract, user_data encoding |
| `src/nxt_service.c` | #30, #31 | Registration ordering, probe gating |
| `src/nxt_epoll_engine.c` | #31 | Shared helpers extracted (signalfd, accept4, recvbuf) |
| `auto/events` | #30 | liburing compile+link probe |
| `auto/options` | #30 | `--io-uring` / `--io-uring-default` flags |
| `docs/io_uring/design.md` | #31 | Engine contract, design notes, bring-up findings (1100 lines) |
| `docs/io_uring/engine-contract.md` | #31 | Verified vtable contract (719 lines) |
| `docs/io_uring/results-stage1.md` | #31 | Stage 1 benchmark results |
| `docs/io_uring/results-stage2.md` | #31 | Stage 2 benchmark results |
| `tools/bench-engines.sh` | #32 | A/B benchmark harness (466 lines) |
| `tools/bench-engines-report.py` | #32 | Markdown report generator (111 lines) |
