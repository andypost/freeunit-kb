# FreeUnit + Buran Research Notes

**Created:** 2026-07-13
**Status:** Ongoing research, to be refined
**Context:** io_uring engine PRs (#30-32), Buran benchmark comparison,
HTTP/2 vs datagram listener discussion, DrupalCon BoF planning

---

## 1. io_uring Event Engine (PRs #30-32)

### Architecture
- **Stage 1 (#30):** Multishot POLL_ADD as "better epoll". Throughput parity,
  CPU +4-50% on accept-heavy paths (thundering herd: no EPOLLEXCLUSIVE analogue).
- **Stage 2 (#31):** Oneshot IORING_OP_ACCEPT (tier ACCEPT). CPU regression
  halved (+7-12% vs +25-50%). Stay-armed-while-BLOCKED removed per-request SQE
  churn. RECV tier deferred (3 structural constraints).
- **Harness (#32):** Build-agnostic A/B benchmark (`tools/bench-engines.sh`).
  Interleaved rounds, noise floor from A/A run, 5 scenarios, oha+ab.

### Kernel version matrix
| Kernel | Feature | Tier |
|--------|---------|------|
| 5.5 | NODROP | Floor |
| 5.11 | EXT_ARG | Floor |
| 5.13 | Multishot POLL_ADD | POLL (floor) |
| 5.19 | IORING_OP_ACCEPT | ACCEPT |
| 6.0 | RECV_MULTISHOT + send_zc | RECV (deferred) |
| 6.0+ | SINGLE_ISSUER + DEFER_TASKRUN | OPT (dropped) |

### Three deferred RECV constraints (structural C limitations)
1. **Scope:** `nxt_fd_event_t` has no type tag → can't distinguish data conns
   from UDS port sockets
2. **Buffer lifetime:** `c->read` raw pointer → can't track ring buffer ownership
   → risk of soak signal-11
3. **Read discipline:** `block_read()` flag vs multishot recv continuous delivery
   → ENOBUFS accumulation

### Key lesson
Kernel features probed via functional runtime tests, never `uname` parsing.
`NXT_IO_URING_FORCE_TIER` simulates any kernel on 7.0 for fallback testing.

---

## 2. Buran Architecture (v0.2.0 — major update 2026-07-13)

**Repo:** github.com/buran-project/buran
**Language:** Rust, edition 2024, minimum 1.88
**Runtime:** tokio (multi-threaded, NOT thread-per-core)
**Version:** 0.2.0 (bumped from 0.1.0)
**NO io_uring** — standard tokio + epoll
**42 files changed, 3072 insertions, 538 deletions** since v0.1.0

### Key architectural changes in v0.2.0

#### 1. BWP protocol redesigned — major frame renumbering
- FrameKind values completely reorganized into groups by direction
- **New frames:**
  - `Flush` — explicit flush-forwards (PHP flush/SSE support)
  - `Done` — separates `fastcgi_finish_request` client release from true task completion
  - `Abort` — router asks worker to abort a specific task by ID
  - `Ping` / `Pong` — liveness probing with status (PONG_IDLE=0, PONG_BUSY=1)
- Frame order by direction: Handshake (1-2) → Request delivery (3-5) → Response (6-12) → Liveness (13-14)
- BWP_VERSION should be bumped to 2 (implicit, not explicit in code)

#### 2. Task timeout system (replaces simple "stuck" detection)
- `limits.response_timeout` — per-event budget (fastcgi finish_request response)
- `limits.task_timeout` — total wall-clock including background (NEW)
- Sweep function runs every tick, finds over-budget tasks
- Two-phase kill: `Abort` frame → grace period → `Ping` probe → `Pong` check → SIGKILL via prototype
- Workers killed by token (from Hello), NOT by PID — pid-reuse safe
- Kill goes through prototype (parent process), not direct SIGKILL

#### 3. Spawner as trait (not closure)
Old: `Spawner = Arc<dyn Fn() -> Result<UnixStream>>`
New: `pub trait Spawn { fn spawn() -> Result<UnixStream>; fn kill(token: u64) }`  
Router no longer signals PIDs directly — asks prototype to kill by token.

#### 4. Processes: auto
```
processes: auto
```
Detects `std::thread::available_parallelism()` capped by cgroup CPU quota
(Docker `--cpus`, k8s `limits.cpu`). Supports cgroup v1 and v2.
`cores_from_quota()` rounds fractional quotas up (1.5 CPUs → 2 workers).

#### 5. Server header: optional version
```yaml
settings:
  http:
    server_version: false  # reveals only "buran", no version
```

#### 6. Host header validation
- RFC 9110 7.2: HTTP/1.1 must carry exactly one Host (reject 0 or 2+)
- Duplicate Content-Length: reject as request-smuggling vector

#### 7. Security hardening
- Config anchors/aliases rejected (YAML injection via `*anchor`)
- SpillGuard: orphaned temp files cleaned on startup, `Drop` guard on failure
- Body files created 0600, chowned to worker uid (not world-readable)
- log field sanitization
- Symlink control: `follow_symlinks` config option
- `initgroups()` before uid/gid switch (complete privilege drop)

#### 8. Stream threshold raised to 256 KiB
Was 96 KiB, now 256 KiB for CAP_BODY_STREAM inline body limit.
Premature flush without headers fixed.

### What stayed the same
- Core: kernel-arbitrated SOCK_DGRAM dispatch (unchanged)
- PHP: embedded SAPI via `sapi_shim.c` (unchanged)
- Worker pool: demand-driven growth, janitor shrink
- BWP: flat request encoding with offset table
- No HTTP/2, no io_uring, no HTTP/3

### Core design (unchanged): Kernel-arbitrated dispatch
```
Request → SOCK_DGRAM (AF_UNIX) → kernel wakes ONE idle worker
Response → UnixStream (per-worker) → router demux by request_id
```
"The MPMC arbitration, the hardest concurrency in this design,
is the kernel's job, not ours." — dispatch.rs

### Crate structure
| Crate | Role |
|-------|------|
| `buran` | Main binary, supervisor, spawner |
| `buran-router` | Accept loop, HTTP/1.1, routing, dispatch, access log |
| `buran-config` | YAML schema, validation, substitution, CPU detection |
| `buran-ipc` | BWP framing, Hello/HelloAck, RequestBuilder/View (0.2.0) |
| `buran-worker` | Worker SDK (Responder, WorkerError) (0.2.0) |
| `buran-php` | PHP SAPI worker (libphp embedded via sapi_shim.c) |
| `buran-echo` | Test/echo worker |

---

## 3. Benchmark Results (from screenshots + PR docs)

### Low concurrency (128 connections, 10s)
| Stack | RPS | p50 | p99 | Success |
|-------|-----|-----|-----|---------|
| Buran (v0.1.0) | 198,529 | 0.59ms | 1.56ms | 100% |
| FreeUnit | 188,730 | 0.53ms | 2.52ms | 100% |
| nginx+FPM | 57,929 | 2.12ms | 3.60ms | 100% |

### C10K (10,000 connections)
| Stack | RPS | p50 | p99 | Success |
|-------|-----|-----|-----|---------|
| Buran (v0.1.0) | 265,201 | 29.5ms | 154ms | 100% |
| FreeUnit | 141,331 | 67.8ms | 102ms | 100% |
| nginx+FPM | 13,494 | 110ms | 1258ms | 96.9% |

> **Note:** v0.2.0 architectural changes (liveness, Abort/Done protocol, task_timeout
> sweep) may affect performance. Re-benchmark after v0.2.0 stabilizes.

### io_uring A/B (from PR #31 docs, kernel 7.0)
| Scenario | Δ throughput (ab) | Δ CPU (ab) | Verdict |
|----------|-------------------|------------|---------|
| ret200_ka_hi | +0.6% | +3.8% | parity |
| ret200_close | -1.5% | +12.5% | slight CPU cost |
| proxy_ka | -8.7% | +11.3% | real regression |
| php_ka | -0.3% | +13.8% | parity |

---

## 4. HTTP/2 vs Datagram Listener

### Why upstream Unit skipped H2
- nginx Inc. model: nginx terminates H2, Unit = app server behind proxy
- `nxt_h1proto.c` hardcoded to 1 fd = 1 request
- H2 requires: stream multiplex, HPACK, flow control, priority

### Datagram listener proposal
Instead of H2 in C-core, add a datagram listener:
- Proxy (Buran/Traefik/HAProxy) terminates H2/H3
- Sends BWP datagram to FreeUnit via AF_UNIX SOCK_DGRAM
- Kernel dispatches to one worker (wake-one, free MPMC)
- Response via UnixStream
- **~700 lines vs ~4000 for H2**

### H2 complexity in C vs Rust
| Aspect | FreeUnit (C) | Buran (Rust) |
|--------|--------------|--------------|
| QUIC stack | quiche (C API) | quinn/s2n-quic |
| HTTP/3 | quiche-h3 or manual | `h3` crate (~100 lines) |
| Event loop | Manual timer + UDP poll | `tokio::select!` |
| Code volume | ~3000-5000 lines | ~200-500 lines |

### OpenSSL 3+ QUIC API
- Available in 3.2+, stable in 3.4+
- Server-side multi-connection still maturing (~50% production-ready)
- Better alternatives: quiche (Cloudflare) or aws-lc + s2n-quic

---

## 5. Impact on Real Applications (Drupal/WP)

### Reality: DB-bound
- Database: 70-90% of request time
- Network/HTTP: 1-3%
- io_uring/BWP: +5-15% overall, not 3x

### Where optimizations help
| Optimization | Benchmark win | Real WP/Drupal | Value |
|---|---|---|---|
| io_uring POLL+ACCEPT | parity | +0% | None for CMS |
| io_uring RECV (zero-copy) | +20-30% projected | +5-10% | Static, uploads |
| Kernel dispatch (BWP) | +3x vs FPM | +10-15% | p99 under load |
| Embedded SAPI | +30% vs FPM | +5% | Per-request overhead |
| Persistent workers + opcache | — | +20-40x vs cold | **Main win** |
| Graceful reload | — | Zero downtime | Deploy safety |

### What Drupal/WP actually needs (priority order)
1. MySQL connection pooling in SAPI
2. In-memory cache bridge (Redis)
3. Preloaded PHP classes (opcache.preload)
4. Graceful reload
5. Kernel-arbitrated dispatch (BWP)
6. io_uring RECV tier

---

## 6. BWP Protocol Evolution (v0.1.0 → v0.2.0)

### What changed
| Aspect | v0.1.0 | v0.2.0 |
|--------|--------|--------|
| Frame count | 13 | 15+ |
| Body streaming threshold | 96 KiB | 256 KiB |
| Liveness | N/A (stuck detection only) | Ping/Pong + Abort/Done |
| Timeout model | single `limits.timeout` | `response_timeout` + `task_timeout` |
| Worker kill | direct SIGKILL by PID | via prototype by token (pid-safe) |
| Spawner | closure | trait (spawn + kill) |
| Flush/SSE | N/A | explicit `Flush` frame |
| fastcgi_finish | `End` only | `End` (client) + `Done` (task) |

### New frame kinds
| # | Name | Direction | Purpose |
|---|------|-----------|---------|
| 9 | Flush | Worker → Router | PHP flush / SSE (forward buffered data, keep stream open) |
| 11 | Done | Worker → Router | Task fully finished (after background work) |
| — | Abort | Router → Worker | Cancel request by ID (timeout) |
| — | Ping | Router → Worker | Liveness probe (request_id = suspected task) |
| — | Pong | Worker → Router | Liveness response (aux: PONG_IDLE=0, PONG_BUSY=1) |

### Implications for FreeUnit BWP adapter
- BWP is now mature enough to anchor a FreeUnit adapter
- Frame numbering stabilized with groups by direction
- Abort/Done protocol handles the timeout problem without killing workers
- Ping/Pong solves liveness (relevant for X4 persistent-worker contract)
- Flush/SSE support means Buran can serve streaming PHP apps
- `processes: auto` with cgroup detection is production-grade

---

## 7. Buran evolution note

> Buran v0.2.0 (2026-07-13) is a major architectural update. Performance
> numbers from v0.1.0 benchmarks may not reflect current state. The BWP
> protocol is stabilizing toward a formal open specification suitable for
> multi-implementation adoption (Buran Rust, FreeUnit C, HAProxy plugin).
