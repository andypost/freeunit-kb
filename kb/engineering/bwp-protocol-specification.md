# BWP (Buran Worker Protocol) v1 — Technical Specification

**Source:** https://github.com/buran-project/buran
**Crates:** `buran-ipc` (protocol), `buran-worker` (SDK), `buran-php` (PHP worker)
**Status:** Production in Buran, v1 stable

---

## 1. Overview

BWP is a **transport-agnostic binary protocol** for communication between an
application server (router) and PHP/application workers.

### Key design decisions

1. **Two channels per worker:**
   - **Work socket** (shared AF_UNIX SOCK_DGRAM) — kernel arbitrates which
     idle worker receives each incoming request datagram. "The MPMC
     arbitration, the hardest concurrency in this design, is the kernel's job,
     not ours." Wakes exactly ONE idle worker per datagram.
   - **Response stream** (per-worker AF_UNIX stream) — responses flow back on
     a private stream, multiplexed by request_id. Router demuxes.

2. **Flat binary encoding for requests:** A contiguous blob with an offset
   table. Worker reads fields by offset WITHOUT re-parsing HTTP and WITHOUT
   copying.

3. **Frame-based protocol:** Fixed 16-byte header + variable payload. 13 frame
   kinds defined.

---

## 2. Wire Format

### 2.1 Frame Header (16 bytes, little-endian)

```
 0    1      2        4            8             12         16
+------+------+--------+------------+--------------+-----------+
| kind | flags|reserved| request_id | payload_len  |   aux     |
| u8   | u8   | u16    | u32        | u32          | u32       |
+------+------+--------+------------+--------------+-----------+
```

- **kind** — FrameKind enum (1-13)
- **flags** — request-specific flags (body mode, upgrade)
- **request_id** — per-request identifier, scoped to one worker's connection
- **payload_len** — length of the payload that follows the header
- **aux** — used for HTTP response status (ResponseHeaders), WebSocket opcode (WsMessage)

### 2.2 Frame Kinds

| # | Name | Direction | Payload | Description |
|---|------|-----------|---------|-------------|
| 1 | Hello | Worker → Router | 20 bytes | Magic + version + pid + concurrency + capabilities |
| 2 | HelloAck | Router → Worker | 8 bytes | Accepted version + granted concurrency |
| 3 | Request | Router → Worker | Variable | Flat binary request (offset table + blob) |
| 4 | ResponseHeaders | Worker → Router | Variable | HTTP status (in aux) + pre-serialized header block |
| 5 | ResponseBody | Worker → Router | Variable | Response body chunk |
| 6 | End | Worker → Router | 0 | Request finished (fastcgi_finish_request analogue) |
| 7 | Error | Worker → Router | Variable | Error message string; router replies 502/503 |
| 8 | Log | Worker → Router | Variable | Log line (printed by router) |
| 9 | Ready | Worker → Router | 0 | Obsolete; tolerated but not needed (kernel dispatch) |
| 10 | Claim | Worker → Router | 0 | "Request id is mine" — diagnostics + stuck tracking |
| 11 | Retire | Router → Worker (work socket) | 0 | Dynamic pool shrink: one idle worker exits gracefully |
| 12 | RequestBody | Router → Worker | Variable | Body chunk for FLAG_BODY_STREAM requests |
| 13 | WsMessage | Both | Variable | WebSocket message, opcode in aux |

### 2.3 Request Flags (byte 1 of header)

| Bit | Name | Description |
|-----|------|-------------|
| 0 | FLAG_BODY_FILE | Preread body field is a temp-file path (body > dgram limit) |
| 1 | FLAG_BODY_STREAM | Body arrives as RequestBody frames on stream after Claim |
| 2 | FLAG_UPGRADE | WebSocket upgrade offer |

### 2.4 Hello/HelloAck Payload

**Hello (20 bytes, worker → router):**
```
 0     4   8-11  12-15  16-19
+------+---+------+------+------+
| MAGIC|VER | PID  | CONC | CAP  |
| BWP\0|u32 | u32  | u32  | u32  |
+------+---+------+------+------+
```

**MAGIC:** `b"BWP\0"` (4 bytes)
**VER:** BWP_VERSION = 1
**PID:** Worker process id (router uses to SIGKILL wedged workers)
**CONC:** Declared concurrency (1 for blocking runtimes, N for event loops, 0=unbounded)
**CAP:** Bitmask of capabilities (bit 0 = CAP_BODY_STREAM, bit 1 = CAP_WEBSOCKET)

**HelloAck (8 bytes, router → worker):**
```
 0-3    4-7
+------+------+
| VER  | CONC |
| u32  | u32  |
+------+------+
```

**CONC (granted):** min(declared, config cap). u32::MAX when both sides unbounded.

### 2.5 Request Payload (flat binary encoding)

```
  0   u32    blob_off  (= table end, from payload start)
  4   (off u32, len u32)  method
  12  (off u32, len u32)  path        — decoded, normalized
  20  (off u32, len u32)  target      — original request target
  28  (off u32, len u32)  query
  36  (off u32, len u32)  version
  44  (off u32, len u32)  remote_addr
  52  (off u32, len u32)  server_name
  60  u64   content_length
  68  u32   app_target    (reserved, 0)
  72  u32   server_port
  76  u32   fields_count
  80  fields_count × (name_off u32, name_len u32, val_off u32, val_len u32)
  ..  (off u32, len u32)  preread body
  ..  blob: concatenated strings referenced by offsets
```

All offsets are relative to blob start (offset table end). The worker reads
fields directly from the blob using offset + length — NO re-parsing, NO copies.

---

## 3. Concurrency Contract

### 3.1 Blocking Runtimes (PHP, concurrency = 1)

```
Worker process (single-threaded):
  1. boot libphp SAPI
  2. handshake (Hello → HelloAck) on private stream
  3. LOOP:
     a. recv() on shared work socket → BLOCK until datagram arrives
     b. decode frame header (16 bytes)
     c. if Request → parse flat binary, call PHP handler
     d. if Retire → exit gracefully (dynamic pool shrink)
     e. build response frames, write_all() to private stream
     f. goto LOOP
```

Worker must NOT `recv()` on work socket when at concurrency limit — staying
out of `recv` is what keeps the kernel balancing load across workers.

### 3.2 Event-Loop Runtimes (Node, Rust, concurrency = N)

Same protocol, but worker declares concurrency > 1 and can have multiple
in-flight requests. Frames of concurrent requests interleave freely on the
response stream in both directions — demultiplexed by request_id.

### 3.3 Dynamic Pool Management

- **Growth:** demand-driven. Pool checks if capacity(in_flight / concurrency_per_worker) <
  spare threshold → spawn new worker.
- **Shrink:** `janitor` goroutine periodically sends Retire datagrams on work
  socket. Exactly one idle worker consumes each, drains its in-flight requests,
  exits. EOF on the private stream signals the router.
- **Stuck detection:** A worker whose every granted concurrency slot is stuck
  (requests timed out) gets SIGKILL. The router accounts for the loss and
  spawns a replacement.

---

## 4. Capabilities

### 4.1 CAP_BODY_STREAM

Workers that declare this capability receive bodies larger than ~96KB as
`RequestBody` frames on their private stream (after Claim), instead of
spilling to a temp file. A zero-length payload terminates the body; worker
compares received bytes with content_length to detect client abort.

### 4.2 CAP_WEBSOCKET

Workers that declare this capability receive WebSocket upgrade offers
(FLAG_UPGRADE). The worker decides:
- **Reject:** answer with regular HTTP response (non-101) → goes to client
- **Accept:** answer 101 → router computes Sec-WebSocket-Accept, owns RFC 6455
  (masking, fragment reassembly, UTF-8 checks, ping/pong never reach worker)

After 101, both sides exchange WsMessage frames. Close from client arrives as
WsMessage/WS_OP_CLOSE. Worker sends End to close. request_id slot stays
occupied for the tunnel's lifetime.

WebSocket opcodes from RFC 6455:
- WS_OP_TEXT = 1
- WS_OP_BINARY = 2
- WS_OP_CLOSE = 8

---

## 5. Crash Semantics

- **Worker death during request:** The request being processed fails. Datagrams
  the dead worker consumed are lost; unconsumed datagrams stay queued for
  surviving workers (kernel SOCK_DGRAM buffer, no loss after consume).
- **Router death:** Workers detect via EOF on private stream → exit.
- **Datagram loss (UDS SOCK_DGRAM):** Routates at capacity will drop datagrams
  (kernel buffer full). On AF_UNIX (not UDP) this is extremely rare. Routers
  use timeout-based retry.

---

## 6. Differences from FastCGI

| Aspect | FastCGI | BWP |
|--------|---------|-----|
| **Transport** | TCP or UDS stream | **SOCK_DGRAM** for requests, stream for responses |
| **Dispatch** | Router must multiplex (select/collect) | **Kernel** wakes exactly one idle worker per datagram |
| **Request encoding** | Raw PARAM/STDIN records | **Flat binary** with offset table — worker reads by offset |
| **HTTP re-parse** | Yes (worker re-builds `$_SERVER`) | **No** — fields available by direct offset lookup |
| **Header format** | Name=value PARAM pairs | Pre-serialized header block in ResponseHeaders frame |
| **Body streaming** | Separate STDIN stream | Inline + file + stream (3 modes) |
| **WebSocket** | Not supported | Native via WsMessage frames + CAP_WEBSOCKET |
| **Concurrency model** | Blocking only (1 req/worker) | **Both**: blocking (1) and event-loop (N) |

---

## 7. Protocol Flow Diagram

```
┌──────────┐                    ┌──────────┐
│  Router  │                    │  Worker  │
└────┬─────┘                    └────┬─────┘
     │   — private stream (UDS) —     │
     │   ─────── Hello ──────────→   │  (magic + version + concurrency + caps)
     │   ←───── HelloAck ─────────   │  (version + granted concurrency)
     │                               │
     │   — shared work socket (SOCK_DGRAM) —
     │          ↑ worker starts idle
     │          ↑ kernel sends datagram to ONE worker
     │   ─────── Request (datagram) ──→   │
     │                               │
     │   — private stream (UDS) —     │
     │   ←────── Claim ────────────   │  (request_id claimed)
     │                               │
     │   (if FLAG_BODY_STREAM)         │
     │   ──── RequestBody frames ──→  │
     │   (if FLAG_UPGRADE + 101)       │
     │   ←───── WsMessage ──────────  │
     │   ────── WsMessage ─────────→  │
     │                               │
     │   ←── ResponseHeaders (aux=status) ──  │
     │   ←── ResponseBody chunk 1 ──  │
     │   ←── ResponseBody chunk 2 ──  │
     │   ←── ResponseBody chunk N ──  │
     │   ←────── End ───────────────  │
     │                               │
     │   (or on error)                │
     │   ←────── Error ──────────────  │
     │                               │
     │   — shared work socket —       │
     │   ──── Retire (datagram) ───→  │  (dynamic pool shrink)
     │   ←── (worker exits) ──────    │  (EOF on private stream)
```

## 8. BWP as Open Protocol

BWP is transport-agnostic by design. In v1 it uses AF_UNIX SOCK_DGRAM for the
work queue and AF_UNIX STREAM for responses. The frame format, Hello
negotiation, and concurrency contract are independent of transport — could be
adapted to TCP, UDP, or shared memory.

The protocol version (BWP_VERSION = 1) allows backward-incompatible evolution
with opt-in capability negotiation.

---

## Questions for Claude / Next Steps

### Implementation in FreeUnit C-core

1. **Scope for FreeUnit:** Should FreeUnit implement BWP as its worker protocol
   (replacing/unifying FastCGI), or implement a BWP-compatible listener for
   receiving requests from a Buran frontend?

2. **X4 persistent-worker contract:** BWP's blocking profile (concurrency=1,
   `recv` → handle → write → `recv` loop) maps directly to the X4
   `nxt_unit_request_loop_t` proposal. Can X4 be designed as a thin C
   implementation of the BWP worker SDK?

3. **Kernel-arbitrated dispatch:** Buran uses shared SOCK_DGRAM for work
   distribution. For FreeUnit with persistent workers, is this a path to
   replacing the current router→worker port queue? Or is the port queue
   fast enough that kernel dispatch isn't needed?

4. **Flat transaction encoding:** Could FreeUnit use BWP's flat request format
   (offset table + blob) for router→worker communication, replacing the
   current multi-message shmem protocol? This would reduce IPC overhead on
   every request.

### Integration with FreeUnit

5. **Dual mode:** FreeUnit could support both traditional HTTP/1.1 listeners
   AND a dgram/BWP listener. The traditional listener serves direct traffic;
   the dgram listener receives requests from Buran (or any BWP-speaking proxy).
   Config:

   ```yaml
   listeners:
     "*:8080":        # Traditional HTTP/1.1
       route: main
     dgram:/run/freeunit/work.sock:  # BWP from Buran
       route: main
       protocol: bwp
   ```

6. **BWP as a FastCGI replacement:** If FreeUnit embedded BWP instead of
   FastCGI for PHP worker communication, the benefits would include:
   - No HTTP re-parse in worker
   - Kernel-arbitrated dispatch
   - Native WebSocket support
   - Concurrency contract for event-loop PHP (TrueAsync)

7. **Response aggregation:** The Write Batcher in `buran-worker` collects all
   response frames into a single `write_all()` per request (headers + body
   chunks + end). FreeUnit could adopt the same pattern for lower syscall
   overhead.

### DrupalCon BoF positioning

8. **Buran + FreeUnit = complete stack:** Buran as H2/H3 edge terminating TLS,
   FreeUnit as PHP application server speaking BWP. Message for Drupal devs:
   "HTTP/3 without nginx, zero-copy without Docker, persistent workers without
   Swoole."
