# Fixing io_uring RECV Tier on Kernel 6.0+

**Problem:** Three C-structural constraints forced the RECV tier's deferral
in PR #31. Kernel 6.0+ has all the features needed — this is a C architecture
issue, not a kernel issue.

---

## The Three Constraints (from PR #31 `design.md`)

### C1: Scope — data conns vs UDS port sockets

> "recv must cover data conns only, never UDS port sockets (SCM_RIGHTS/cred
> cmsgs). But both arm read through the same `enable_read` and `nxt_fd_event_t`
> has no type tag to separate them — and §1.7 forbids adding one."

### C2: Buffer lifetime — ring buffer across app round-trip

> "The zero-copy win needs a ring buffer handed to the pipeline as `c->read`,
> but the router can pin `c->read` across the app round-trip and starve the
> ring; the safe answer is copy-out at the parse boundary, and a naive
> copy-out-everywhere model adds a userspace copy that makes it net-negative.
> A lifecycle slip is a soak signal-11."

### C3: Read discipline — block_read vs multishot recv

> "Unit `block_read()`s after each read while multishot recv delivers
> continuously, so a blocked conn accumulates ring buffers until ENOBUFS and
> the degrade-to-poll+recv path must be robust."

---

## Kernel 6.x Features Available

| Kernel | Feature | Solves |
|--------|---------|--------|
| 6.0 | `IORING_RECV_MULTISHOT` + provided buffer rings | C2, C3 |
| 6.0 | `IORING_OP_SEND_ZC` (zero-copy send) | C2 (send side) |
| 6.0 | `IORING_SETUP_SINGLE_ISSUER` + `DEFER_TASKRUN` | Performance (not a constraint) |
| 6.0+ | `IORING_REGISTERED_BUFFERS` (`IO_URING_REG_USE_REGISTERED_*`) | C2 — pin pages, no buffer starvation |
| 6.1+ | `IORING_OP_READ_FIXED` stability | C2 — read into registered buffers |
| 6.4+ | `IORING_SETUP_COOP_TASKRUN` improvements | Performance |
| 6.7+ | `send_zc` with `IORING_NOTIF_USAGE` | C2 — notification for buffer reuse |

---

## Fix Strategy per Constraint

### C1 Fix: Socket Type Tag — the §1.7 exception

§1.7 forbids adding fields to `nxt_fd_event_t` because it's a hot cache path.
But we can use the **existing** `nxt_fd_event_t` fields already allocated:

```c
// nxt_fd_event_t — current structure
typedef struct nxt_fd_event_s {
    // ... existing fields ...
    uint8_t           read;         // state (INACTIVE/DISABLED/BLOCKED/...)
    uint8_t           write;        // state
    uint8_t           epoll_eof;    // exists now (set-only from CQE handler)
    uint8_t           epoll_error;  // exists now
    
    // Proposal: reuse one of the spare alignment bytes for type tag
    // None exist currently, so add:
    uint8_t           conn_type:2;  // 0=tcp, 1=uds, 2=listen, 3=internal
    // 6 spare bits remain; still fits in the alignment budget
} nxt_fd_event_t;
```

**But §1.7 isn't the end of the story.** The real question: does the
`nxt_event_interface_t` contract pass enough context to the engine's
`enable_read` to distinguish conn types?

Currently `enable_read(engine, ev)` receives `nxt_fd_event_t *ev`, which has
NO access to the parent `nxt_conn_t` or its type. The fix:

**Option A (minimal):** Extract conn type from the fd itself:
```c
void nxt_io_uring_enable_read(nxt_event_engine_t *engine, nxt_fd_event_t *ev) {
    // At accept time, we know the fd type. For UDS sockets:
    struct sockaddr_un addr;
    socklen_t len = sizeof(addr);
    if (getsockname(ev->fd, (struct sockaddr *)&addr, &len) == 0
        && addr.sun_family == AF_UNIX)
    {
        // → UDS: use poll-mode (no buf_ring recv)
        arm_poll_read(engine, ev);
    } else {
        // → TCP: use completion-mode recv (buf_ring)
        arm_buf_ring_recv(engine, ev);
    }
}
```
**Cost:** one `getsockname(2)` syscall on the first `enable_read`. After that,
cache the result in a `conn_type` bit.

**Option B (clean):** Add the `conn_type` field to `nxt_fd_event_t` (violating
§1.7 but pragmatically simpler). The `nxt_event_interface_t` design explicitly
allows engine-specific extensions:
```c
// nxt_io_uring_engine.c — io_uring extends nxt_fd_event_t
#define NXT_IO_URING_CONN_TCP    0
#define NXT_IO_URING_CONN_UDS    1
#define NXT_IO_URING_CONN_LISTEN 2

// in enable_read:
if (ev->nxt_io_uring_conn_type == NXT_IO_URING_CONN_UDS) {
    // → poll-mode (SCM_RIGHTS need raw recvmsg)
} else {
    // → completion-mode (buf_ring recv)
}
```

### C2 Fix: Two Buffer-Lifecycle Strategies

#### Strategy A: Copy-at-Parse (safe, net-positive for large bodies)

The PR's concern was correct: **copying every small request** makes it
net-negative. But we can use a **size heuristic**:

```c
// nxt_io_uring_recv_steal — called at the request-parse boundary
void nxt_io_uring_recv_steal(nxt_io_uring_conn_t *conn, nxt_buf_t *dst) {
    if (conn->recv_buf_size > IO_URING_STEAL_THRESHOLD) {
        // Check threshold: ~4KB
        // → Zero-copy: hand the ring buffer pointer to the pipeline
        dst->mem.pos = conn->ring_buf;
        dst->mem.free = conn->ring_buf + conn->recv_buf_size;
        dst->mem.start = conn->ring_buf;
        dst->mem.end = conn->ring_buf + IO_URING_BUF_SIZE;
        // Mark buffer "owned by the pipeline" — the ring slot cannot
        // be reused until this buf is freed.
        conn->buf_in_flight = true;
        // On buf free: call io_uring_buf_ring_add() to return it
    } else {
        // → Copy-out for small bodies (<4KB)
        memcpy(dst->mem.pos, conn->ring_buf, conn->recv_buf_size);
        io_uring_buf_ring_add(br, conn->ring_buf, IO_URING_BUF_SIZE,
                              conn->buf_index, IO_URING_BUF_FLAG);
        // Buffer immediately returned to ring
    }
}
```

**Threshold logic:**
```c
#define IO_URING_STEAL_THRESHOLD 4096
// Bodies ≤4KB: copy-out, return buffer to ring immediately
// Bodies >4KB: steal the buffer, pipeline owns it, return on free

// Rationale:
// - HTTP headers (~1-2KB): copied, no buffer starvation
// - PHP uploads (5MB+): stolen, zero-copy win
// - JSON API (500B-10KB): mixed, threshold catches the 10KB ones
// - Use profile: Drupal/WP uploads are 100KB-50MB → mostly steal
```

#### Strategy B: Registered Buffers (IO_URING_REGISTERED_BUFFERS)

Kernel 6.0+ allows registering a set of buffers at ring creation time.
The kernel **pins the pages** — buffers never leave system memory.
When c->read is pinned across the app round-trip:

```c
// Setup (once per ring):
io_uring_register_buffers_sparse(ring, 128, &buf_config);
// Creates 128 registered buffer slots — kernel pins pages

// Per-recv: kernes can write into registered buffer
sqe = io_uring_get_sqe(ring);
io_uring_prep_recv_multishot(sqe, fd, 0, BUFSEL_FIXED);
sqe->buf_group = 0;  // uses registered buffer group
sqe->flags |= IOSQE_BUFFER_SELECT | IORING_RECV_MULTISHOT;

// Per-completion:
// CQE carries buf_index — which registered buffer was used
// c->read = pointer to the registered buffer (always in memory)
// Pipeline reads directly from it
// When pipeline is done — mark buffer as available for reuse
```

**Key advantage over buf_ring:** registered buffers are **never ENOBUFS**.
The kernel guarantees them as long as the ring is alive. The problem in the
PR's analysis (closing stale fd) becomes **zero risk** because the registered
buffer lives with the ring, not the fd.

#### Strategy C: Dynamic Two-Pool (recommended hybrid)

```c
// Two buffer pools per connection:
// 1. Small slab (64 bytes × N) — for headers
// 2. Large buffer (64KB × M) — for body

// Headers always go through the small slab (copy-out, instant return)
// Body goes through the large pool (stolen if >4KB, copied if ≤4KB)

struct nxt_io_uring_buf_pool {
    struct io_uring_buf_ring *small;  // 64B × 1024 headers
    struct io_uring_buf_ring *large;  // 64KB × 64 body slots
};

void nxt_io_uring_recv_to_pipeline(nxt_conn_t *c, nxt_buf_t *dst) {
    if (c->state == NXT_CONN_PARSE_HEADERS) {
        // Headers: always copy (small, frequent → buffer ring starvation is unacceptable)
        copy_from_small_slab(c, dst);
        return_small_slab_buffer(c);
    } else {
        // Body: steal if size > threshold
        if (c->body_remaining > IO_URING_STEAL_THRESHOLD) {
            steal_large_buffer(c, dst);
        } else {
            copy_from_large_slab_small_body(c, dst);
        }
    }
}
```

### C3 Fix: block_read × multishot recv

The problem: `block_read()` is a pure state write. In epoll mode, the
registration stays armed and nothing happens. In io_uring multishot mode,
the kernel keeps delivering — buffers fill up → ENOBUFS.

**Fix: Two-phase recv connection I/O**

```c
static nxt_conn_io_t nxt_io_uring_multishot_conn_io = {
    .recv = nxt_io_uring_recv_multishot,     // arm multishot + buf_ring
    .send = nxt_conn_send,                   // unchanged
    .close = nxt_io_uring_close,
};

static nxt_conn_io_t nxt_io_uring_oneshot_conn_io = {
    .recv = nxt_io_uring_recv_oneshot,       // re-arm per read
    .send = nxt_conn_send,
    .close = nxt_io_uring_close,
};
```

The engine switches between them based on connection state:

```c
// In enable_read:
void nxt_io_uring_enable_read(nxt_event_engine_t *engine, nxt_fd_event_t *ev) {
    if (ev->state == NXT_EVENT_BLOCKED && ev->io == &nxt_io_uring_multishot_conn_io) {
        // WAS multishot, now BLOCKED → switch to oneshot
        // Cancel pending multishot recv
        io_uring_prep_cancel64(sqe, ud, 0);
        // Mark for re-arm as oneshot on next unblock
        ev->io = &nxt_io_uring_oneshot_conn_io;
        return;
    }
    if (ev->state == NXT_EVENT_DEFAULT && ev->io == &nxt_io_uring_oneshot_conn_io) {
        // Unblocked → can use multishot again
        ev->io = &nxt_io_uring_multishot_conn_io;
    }
}

// In recv_multishot handler — when !F_MORE:
static void nxt_io_uring_recv_multishot_cqe(nxt_io_uring_conn_t *conn,
                                            struct io_uring_cqe *cqe) {
    if (!(cqe->flags & IORING_CQE_F_MORE)) {
        // Multishot terminated (ENOBUFS, kernel pressure)
        // → fall back to oneshot immediately
        conn->ev.io = &nxt_io_uring_oneshot_conn_io;
        // The fallback is transparent: next recv() uses oneshot
    }

    if (cqe->res == -ENOBUFS) {
        // Buffer ring exhausted — drain what we have, re-arm with small buffer
        io_uring_prep_recv(oneshot_sqe, conn->fd, small_buf, sizeof(small_buf), 0);
    }
}
```

**The actual fix is NO multishot for blocking workers:**
```c
// Key insight: Unit routers are BLOCKING. One request at a time per worker.
// Multishot only helps event-loop workers (Python async, Node, Ruby Fiber).
// For blocking workers: use ONESHOT recv (re-arm per recv).

// Oneshot recv has zero ENOBUFS risk:
// → recv() returns data → handler processes → re-arms recv
// → block_read() means DON'T re-arm → no kernel state to cancel
// → enables after block → re-arms → simple!

// This makes all three constraints disappear:
// C1: Scope — oneshot recv for TCP, raw recvmsg for UDS → trivial
// C2: Lifetime — oneshot buf is consumed in handler → no cross-roundtrip pinning
// C3: Discipline — block_read = don't re-arm → no ENOBUFS

// Multishot only for event-loop workers (Python/Ruby async):
// → They CAN handle ENOBUFS (event-loop drains in time)
// → They WANT multishot (reduces syscalls)
// → They can use buf_ring (properly)
```

---

## Architectural Options for FreeUnit C-core

### Option 1: Minimal — oneshot recv only (no multishot for v1)

```c
// nxt_io_uring_engine.c — add oneshot recv
static nxt_conn_io_t nxt_io_uring_oneshot_conn_io = {
    .recv = nxt_io_uring_recv_oneshot,
    .send = nxt_conn_send,  // unchanged
    .close = nxt_io_uring_close,
};

// arm_recv_oneshot(conn, fd, buf, len) → SQE: IORING_OP_RECV
// CQE: handler reads `cqe->res` bytes, processes, re-arms
// block_read: set state, DON'T re-arm
// enable_read: re-arm recv
// close: NO cancel needed (oneshot already consumed)

// One recv = one SQE = one CQE = one handler run
// Simple. Testable. No ENOBUFS.
```

**Pros:** Zero new constraints. Works on kernel 5.19+. No buf_ring needed.
**Cons:** Every recv = one syscall. No zero-copy. Same as plain recv(2).

### Option 2: Hybrid — one-hot recv for blocking, multishot for event-loop

```c
// On accept: determine if this worker is blocking or event-loop
// Blocking → oneshot recv
// Event-loop → multishot recv + buf_ring
if (worker_type == WORKER_BLOCKING) {
    conn->recv_mode = ONESHOT;
} else {
    conn->recv_mode = MULTISHOT;
}
```

**Pros:** Zero-overhead for blocking workers, zero-copy for event-loop.
**Cons:** Two code paths, more testing.

### Option 3: Full — oneshot + multishot + dynamic fallback (recommended)

```c
// Start every conn in MULTISHOT (buf_ring + IORING_RECV_MULTISHOT)
// On ENOBUFS or BLOCK → fall back to ONESHOT (transparent)
// On unblock → try MULTISHOT again
//
// This handles ALL patterns optimally:
// - Long-lived keepalive: multishot (zero syscalls after first recv)
// - Blocked upstream: fall to oneshot (no buffer accumulation)
// - Large upload: buf_ring steal (zero-copy)
// - Small request: buf_ring copy-fast (header optimization)
```

---

## Kernel 6.x Features That Change the Trade-offs

### 6.0: Buffer rings + IORING_RECV_MULTISHOT

The buf_ring API:
```c
// Setup (once per ring):
struct io_uring_buf_ring *br = io_uring_setup_buf_ring(ring, 1024, 0, 0, &ret);
// io_uring_buf_ring_add() to populate
// Kernel writes into ring buffers directly
// CQE returns (buf_off, buf_index) — you read from `br->bufs[buf_index].addr + buf_off`
```

**Changes C2 analysis:**
Before 6.0: buf_ring didn't exist → zero-copy meant custom page-pinning.
After 6.0: `io_uring_setup_buf_ring()` gives you ring buffers in 3 syscalls.

### 6.0: IORING_OP_SEND_ZC

```c
io_uring_prep_send_zc(sqe, fd, buf, len, flags, 0);
// Kernel maps userspace pages, sends directly from them
// No copy from userspace to kernel.
// Notification via IORING_OP_NOTIFY — sent when kernel is done with pages.
```

For Drupal/WP: static file serving via send_zc = zero-copy from page cache
to socket. Combined with `splice()` for sendfile equivalent.

### 6.4+: SINGLE_ISSUER + DEFER_TASKRUN

Not usable in Unit (create ≠ poll thread), but relevant for Buran.

---

## Implementation Plan for FreeUnit

### Phase 1: oneshot recv (kernel 5.19+, ~1 week)

```c
// 1. Add nxt_io_uring_conn_io with oneshot recv
// 2. arm_recv_sqe(fd, buf, len, user_data)
// 3. handler: read bytes → process → (re-arm OR stop)
// 4. block_read = set state, DON'T re-arm
// 5. enable_read = re-arm if state changed from BLOCKED
// 6. close = no-op (oneshot already consumed)

// Files to modify:
// src/nxt_io_uring_engine.c    — add recv_oneshot handler + arming
// src/nxt_fd_event.h           — (maybe) add conn_type field
// docs/io_uring/design.md      — update tiers, add RECV section
```

**Verification:**
- `NXT_IO_URING_FORCE_TIER=recv` enables oneshot recv
- `NXT_IO_URING_FORCE_TIER=accept` keeps Stage-2 ACCEPT path
- Benchmark: RPS, p50/p99, CPU µs/req vs epoll

### Phase 2: buf_ring recv (kernel 6.0+, ~2 weeks)

```c
// 1. Setup buf_ring at ring creation
// 2. IORING_RECV_MULTISHOT with buffer select
// 3. CQE handler: extract buf_index, steal or copy per threshold
// 4. Buffer lifecycle: return to ring on nxt_buf_t free
// 5. ENOBUFS fallback to oneshot recv
```

### Phase 3: send_zc (kernel 6.0+, ~1 week)

```c
// 1. IORING_OP_SEND_ZC for response body
// 2. Notification tracking via fence-style completion
// 3. Static file sendfile → send_zc on the same fd
```

---

## Summary: What Changes on Kernel 6.x

| Constraint | Before 6.0 | After 6.0 | Fix |
|---|---|---|---|
| C1 (Scope) | No way to distinguish | Still no way | Add conn_type bit |
| C2 (Buffer life) | buf_ring doesn't exist; c->read pinning = signal-11 risk | `io_uring_setup_buf_ring()` + registered buffers | Heuristic: steal >4KB, copy ≤4KB; or use registered buffers |
| C3 (Read discipline) | block_read leaves multishot armed → ENOBUFS | Same | Oneshot recv for blocking workers; multishot only for event-loop |

**Bottom line:** Kernel 6.x doesn't automatically fix the three constraints.
It gives us the BUILDING BLOCKS (buf_ring, send_zc, registered buffers) but
the ARCHITECTURAL DECISIONS (how to handle c->read lifetime, how to
distinguish conn types, how to manage block_read) remain C-code design
choices. The RECV tier can be implemented NOW on kernel 6.x — it was deferred
because of C design, not kernel availability.
