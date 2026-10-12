# FreeUnit Roadmap: Active Work & Weak Spots

## Currently Being Fixed (from roadmap, 2026)

### D3: Body Streaming & Buffering (Month 5, ~2 weeks)

**The problem:**

```
Today:
  Client → TCP → Router: recv() entire 50MB body → buf in RAM → IPC → Worker
                                                      ↑
                                               50MB buffer in router RAM
  × 500 concurrent uploads = 25 GB router RAM
  Router runs out of memory → OOM kill
```

**The fix (D3 + BWP body streaming):**

```
After D3:
  Client → TCP → Router: recv() chunk-by-chunk → IPC frame → Worker
                    8KB → frame → worker
                    8KB → frame → worker
                    ...
                    8KB → frame (len=0, end)
  Router never buffers full body. Max RAM = chunk size × concurrent streams.
  With 8KB chunks × 500 streams = 4 MB (was 25 GB).

After BWP:
  Client → Buran (H2/H3 edge) → BWP RequestBody frames → FreeUnit
  Router doesn't even see the body — it goes directly to the worker.
  Zero buffering in router. Zero memcpy for body.
```

**Current status:** In roadmap, not implemented. D3 targets the buffering
audit in `nxt_h1proto.c` and the libunit body path.

---

### X4: Persistent-Worker Contract (Month 5, ~3 weeks)

**The problem:**

```
Today (FPM model):
  Worker starts → PHP boot (500ms cold) → handle 1 request → exit
  Next request → Worker starts → PHP boot (500ms cold) → handle 1 request → exit
  Every request pays boot cost.

  With opcache: boot down to 20ms (all files cached in SHM).
  But: 20ms × 1M requests/day = 5.5 hours wasted on boot per day.
  And: opcache still cold for NEW workers (each fills independently).
```

**The fix (persistent worker):**

```
After X4+P4:
  Worker starts ONCE → PHP boot (500ms) → opcache filled
    ↓
  Loop:
    handle request 1  (0ms boot)
    handle request 2  (0ms boot)
    handle request N  (0ms boot)
  → Max requests > 0 → recycle gracefully (FPM pm.max_requests style)
```

**Current status:** X4 (libunit contract: `nxt_unit_request_loop_t`) designed,
not implemented. P4 (PHP worker mode) depends on X4.

---

### Prototype+Fork: Shared opcache (Research, ~6-8 weeks)

**The problem:**

```
Today:
  Worker 1 boot → opcache SHM (256 MB) created → owns it
  Worker 2 boot → opcache SHM (256 MB) created → ALSO owns its own
  Worker 8 boot → opcache SHM (256 MB) created → 8 × 256MB = 2 GB wasted

  APCu: Worker 1 → apcu_store('config', $data) → only Worker 1 sees it
        Worker 2 → apcu_fetch('config') → MISS
```

**The fix (Buran model — prototype+fork):**

```
After:
  Prototype boot (once) → opcache SHM (256 MB) COW-shared
    ↓ fork
  Worker 1 → inherits SHM → reads same opcache
  Worker 2 → inherits SHM → reads same opcache
  Worker 8 → inherits SHM → 256 MB total (not 2 GB)

  APCu: Worker 1 → apcu_store('config', $data)
        Worker 2 → apcu_fetch('config') → HIT (same SHM segment!)

  Preload: run once in prototype, 7500 Drupal files precompiled, all workers inherit.
```

**Current status:** Buran has this. FreeUnit needs a prototype process layer.
Router can't fork (multithreaded event loop), so prototype runs separately.
Estimated 6-8 weeks.

---

### io_uring RECV Tier (Deferred PR #31, ~2-3 weeks)

**The problem:**

```
Today:
  epoll_wait() → EPOLLIN
  recv(fd, buf, len)  ← one syscall per data arrival
  HTTP parse
  Worker dispatch
  Worker response
  writev(fd, iov)     ← one syscall per response
```

**The fix (io_uring RECV + send_zc):**

```
After:
  io_uring with IORING_OP_RECV_MULTISHOT + buf_ring
  Kernel writes directly into ring buffers → NO recv syscall at all
  Ring buffer → HTTP parse → Worker dispatch
  Worker response → IORING_OP_SEND_ZC → kernel sends from user pages
  Zero copies for static files. Zero syscalls for data arrival.

  CPU saved: recv/writev syscalls eliminated
  RAM saved: zero-copy for body > 4KB (steal buffer)
```

**Current status:** Deferred. 3 C-structural constraints need solving:
1. Scope: distinguish TCP from UDS sockets (no type tag on nxt_fd_event_t)
2. Buffer lifetime: ring buffer across app round-trip (c->read pinning)
3. Read discipline: block_read vs multishot ENOBUFS

Fix plan exists: oneshot recv (Phase 1, kernel 5.19+) → buf_ring (Phase 2, 6.0+) → send_zc (Phase 3, 6.0+).

---

### HTTP/2 Router (D2, ~3 months)

**The problem:**

```
Today:
  HTTP/1.1 only. One connection = one request at a time.
  Client needs 10+ connections for parallel assets (CSS, JS, images).
  Head-of-line blocking: slow resource blocks fast resources.
```

**The fix:**

```
After D2:
  HTTP/2 multiplex: one TCP connection → multiple streams
  Stream 1: GET /index.html
  Stream 2: GET /styles.css  (parallel, no blocking)
  Stream 3: GET /app.js       (parallel, no blocking)
  HPACK header compression → fewer bytes on wire
  Server push (optional) → push critical CSS before client asks
```

**Current status:** Planned, not started. 3 months estimate.
Alternative: Buran as H2/H3 frontend, FreeUnit behind via BWP.

**2026-09-13:** grounded re-check (upstream #388 history, tree grep, ALPN
absence, D3 prerequisite, gRPC/H3 price changes) appended to
`strategy/freeunit-2-3-vision.md` → "2026-09-13 Refresh — HTTP/2 in Unit".

---

## Weak Spots (Architectural Gaps)

### 1. Body Buffering in Router ❌

```
Every request body is buffered in full before worker sees it.
- 50MB upload → 50MB router RAM
- Large file upload → OOM risk
- POST with big JSON → unnecessary memory
```

Fix: D3 (streaming) + BWP (zero-copy body).

### 2. No opcache Sharing Across Workers ❌

```
8 workers = 8 copies of opcache bytecode.
8 × 256MB = 2GB for the same cached PHP files.
```

Fix: Prototype+fork (one opcache SHM, inherited by fork).

### 3. Cold PHP Boot Per Worker ❌

```
Every new worker pays PHP boot cost:
- Cold: 500ms (Drupal, no opcache yet)
- Warm: 20ms (opcache hit, modules loaded from SHM)
- P4: 0ms (loop handles requests, boot once)
```

Fix: P4 persistent worker.

### 4. No DB Connection Pooling ❌

```
Every PHP request: new PDO → TCP handshake → MySQL connect → query → disconnect
TCP handshake: 0.5ms. MySQL auth: 1ms. Per request: 1.5ms wasted.

1000 req/s → 1.5 seconds CPU burned on TCP handshakes per second.
```

Fix: P4 persistent worker → PDO connection reused across requests.

### 5. Single Request Per Worker ❌

```
Worker can process ONE request at a time.
If request takes 45ms (Drupal), worker does nothing else for 45ms.
Throughput = workers / avg_response_time.
8 workers / 45ms = 177 req/s max for Drupal.

With TrueAsync: one worker handles N concurrent requests via fibers/events.
8 workers × 50 concurrent = 400 req/s or more.
```

Fix: TrueAsync (PHP fork, experimental) → concurrent requests in one process.

### 6. No Response Streaming from Worker ❌

```
Worker generates full response → sends to router → router buffers → client.
SSE (Server-Sent Events) → works but no explicit flush support.
Long-running responses → client waits for everything.
```

Fix: X4 persistent-worker contract + Flush semantics (BWP Flush frame).

### 7. TCP/TLS Handshake Per Connection ❌

```
Modern HTTP: client opens 6 connections to load a page.
6 × TCP handshake + 6 × TLS handshake = latency cost.
HTTP/2: one connection, multiplexed streams. H/3: 0-RTT via QUIC.
```

Fix: D2 (HTTP/2) or Buran frontend (H2/H3 termination).

---

## What's NOT a Problem (Stable)

| Component | Status | Why |
|-----------|--------|-----|
| IPC router↔worker | ✅ Fast | UDS + shared memory, <0.1% of request time |
| HTTP parse | ✅ Fast | ~90µs, well-optimized |
| Route match | ✅ Fast | ~5µs, hash-based |
| Config reload | ✅ Working | Live config change, no restart |
| Isolation (cgroups/rootfs) | ✅ Working | Namespaces, openat2, seccomp-ready |
| Graceful shutdown | ✅ 1.36.0 | SIGQUIT + two-phase listener drain |
| OpenTelemetry | ✅ 1.36.0 | OTLP HTTP+gRPC, W3C traceparent |

---

## Priority vs Impact Matrix

```
Impact (user-visible)
  HIGH │                            P4 persistent worker ★
       │                            (Drupal: 500ms→0ms boot)
       │
       │  D3 body streaming   ★     Prototype+fork ★
       │  (OOM prevention)          (opcache 8×→1× RAM)
       │
       │  X4 contract   ★          D2 HTTP/2 ★
       │                            (multiplex, no HOL blocking)
 MEDIUM│
       │  io_uring RECV   ●         TrueAsync   ●
       │  (CPU: -recv syscall)      (concurrent requests)
       │
       │  Structured JSON logs  ●
   LOW │
       └────────────────────────────────────────────
            LOW            MEDIUM            HIGH
                        Effort (weeks to implement)
```

**Now (< 3 months):** P4 persistent workers + prototype+fork (highest user impact)
**Soon (< 6 months):** D3 body streaming + X4 contract + D2 H/2
**Later (> 6 months):** io_uring RECV, TrueAsync, structured logs
