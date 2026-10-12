# Event-Loop & I/O Alternatives to io_uring (FreeUnit C-core)

**Created:** 2026-09-28
**Context:** follow-up to the io_uring decision (PRs #30–32 abandoned as default engine,
see `io-uring-ab-benchmark-approach`, `io-uring-distro-availability`).
Question: what else is on the table, given that even libuv backed off io_uring?

## Reference point: what libuv actually did

- v1.45.0 (2023) introduced io_uring — **for file operations only**, never as the
  network loop. It broke builds on ARM.
- Node.js **disabled io_uring by default** in 20.11.1 (`686da19`), before the ARM fix.
- libuv v1.47.0 fixed ARM; v1.49.0 **disabled SQPOLL by default** (#4492).
- Consumers still bundling an old libuv fail noisily into the epoll+threadpool fallback
  whenever a container's seccomp profile denies `io_uring_setup` (default in K8s).
- Net effect: the event loop stayed epoll; what remains of io_uring in libuv is
  auxiliary (batching), not a mechanism replacement.

Conclusion for us: this is the same shape as our own result — io_uring pays for **file
I/O**, not for socket readiness. The socket loop has cheaper alternatives.

## What FreeUnit already has (verified in `src/`, 2026-09-28)

| Present | Where |
|---|---|
| `epoll`, `signalfd`, `eventfd` | `nxt_epoll_engine.c`, `nxt_event_engine.c` |
| **`EPOLLEXCLUSIVE`** | `nxt_epoll_engine.c:579` — listener herd already mitigated |
| `sendfile` (static files) | `nxt_linux_sendfile.c` |
| `fork()` + epoll, no `clone3` | process model |

## What is absent (grep of `src/` returns nothing)

`splice`/`vmsplice` (comment only), `recvmmsg`/`sendmmsg`, `MSG_ZEROCOPY`,
`TCP_ZEROCOPY_RECEIVE`, kTLS (`SOL_TLS`/`TLS_TX`/`TLS_RX`), `SO_REUSEPORT`,
`SO_BUSY_POLL`, `timerfd_create`, `io_uring`.

## Layer 1 — keep the readiness model, remove the per-event cost

- **Batched I/O**: `recvmmsg`/`sendmmsg` (+ `MSG_WAITFORONE`), an `accept4` loop per
  wakeup, `epoll_pwait2` (5.11) for ns timeouts. Cheap, incremental, no new fallback path.
- **`SO_REUSEPORT`** (3.9) with per-worker listeners + optional
  `SO_ATTACH_REUSEPORT_EBPF` (4.5): the kernel distributes connections wake-one, which is
  structurally what Buran gets from its shared datagram socket — without an accept path in
  the router at all. Also the known route to zero-downtime router restart.
- **`SO_BUSY_POLL` / `SO_INCOMING_CPU`** + RPS/RFS/IRQ placement: the syscall-overhead
  win at C10K without changing any API.
- **Zero-copy on the data path**: `MSG_ZEROCOPY` (4.18) for user-page sends,
  `TCP_ZEROCOPY_RECEIVE` (4.18) for receive, `splice`/`vmsplice` (socket↔pipe). This is
  the prize that the io_uring RECV tier was chasing — reachable over epoll.
- **kTLS** (`TLS_TX`/`TLS_RX`, 4.13): move TLS crypto into the kernel. Frequently a larger
  CPU win than `send_zc` and it composes with the existing connection FSM.

## Layer 2 — change the model, still without a completion API

- **Thread-per-core, shared-nothing**: each worker owns its listener and its own epoll.
  This is precisely the change that makes `SINGLE_ISSUER`/`DEFER_TASKRUN` usable in Rust
  and unusable in our scheme (ring created on router-main, polled on a worker thread).
- **Kernel-arbitrated dispatch (BWP)**: `AF_UNIX SOCK_DGRAM` wake-one work queue instead
  of router-managed arbitration (~700 LOC vs ~4000 for H2). Buran's 265k vs 141k at C10K
  comes from this, not from io_uring.
- **Embedded SAPI** (FrankenPHP/Buran): deletes the IPC hop entirely — but conflicts with
  our per-app uid/namespace isolation and multi-language module design. A different
  product, not a drop-in.
- **Persistent workers + prototype/fork** (X4/P4): measured 0.42 s cold → 0.05 s warm per
  tick (`fork-spawn-drupal-measurement`). Bigger effect on real CMS workloads than any
  event-loop change.
- **D3 body streaming**: removes the full-body buffering in the router (50 MB uploads).

## Layer 3 — other completion APIs

- `libaio`: block devices only, no sockets. POSIX AIO: thread pool, strictly worse.
- `kqueue` / IOCP: the other real completion/notification designs, wrong platforms for us.
- `AF_XDP` / `DPDK`: network in userspace; disproportionate for an application server
  (and it would own the NIC, not just the loop).

## Layer 4 — push the work out of the process

TLS / HTTP2 / HTTP3 termination belongs to the edge (Buran, Traefik, HAProxy); FreeUnit
takes HTTP/1.1 or BWP. Already the strategic direction in `transport-layer-strategy`.

## Recommended order

1. `SO_REUSEPORT` + batched `accept`/`recv` (distribution + fewer syscalls, no new model)
2. `MSG_ZEROCOPY` / `TCP_ZEROCOPY_RECEIVE` + `splice` on the data path
3. kTLS
4. thread-per-core listener ownership
5. BWP datagram listener (structural)

io_uring is not deleted from the roadmap — it stays opt-in (`--io-uring`, epoll fallback)
and its credible use is **file I/O**, not the socket loop.

## Docs check via Context7 (2026-10-11)

Asked the Linux kernel documentation corpus (`/websites/kernel_doc_html`); the wrapper and its
limits are recorded in the `context7-docs` skill.

- **Confirmed, with an added constraint**: `MSG_ZEROCOPY` is documented together with the
  requirement that "the user must not modify the buffer while the send is in progress", and a
  zerocopy failure returns `-1` with `ENOBUFS`. FreeUnit's sendbuf lifetime rules have to satisfy
  that before item 2 of the order below is implemented — the same class of constraint the kTLS
  device-offload path carries.
- **New requirement for kTLS RX (item 3)**: the kernel documents that TLS control messages arrive
  through a cmsg, and that "if no cmsg buffer is provided, an error is returned when a control
  message is received. Data messages can be received without a cmsg buffer." A `TLS_RX` build must
  therefore always pass a control-message buffer on receive, or an incoming alert/close_notify
  turns into an error.
- **Not verifiable from this corpus**: the version floors quoted above — `epoll_pwait2` (5.11),
  `MSG_ZEROCOPY`/`TCP_ZEROCOPY_RECEIVE` (4.18), `kTLS` (4.13), `io_uring` (5.1). The kernel-docs
  corpus does not index man-pages and states no "since Linux N.N" for these APIs. Those numbers
  stay on the man-pages reading and are flagged unverified-by-docs, which is not the same as wrong.
