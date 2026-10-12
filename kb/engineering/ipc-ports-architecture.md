# FreeUnit IPC Ports — Architecture Reference

**Created:** 2026-08-22
**Source:** code walk (src/nxt_port*.c/h), PR #208-#212 context
**Purpose:** How internal IPC ports work, transports, lifecycle, security
boundary. Reference for review and porting discussions.

---

## What a port is

`nxt_port_t` — a **socketpair channel between two processes** plus a
shared-memory message queue. Every process in the system (main, controller,
router, prototype, worker) holds ports to its neighbours.

```
main ←→ controller
main ←→ router (socketpair + queue)
router ←→ prototype ←→ worker
```

## Two transport layers

### 1. Small messages — Unix SOCK_DGRAM + SCM_RIGHTS

`nxt_port_send_msg_t` via `sendmsg()`:

```c
typedef struct {
    nxt_buf_t        *buf;      /* payload */
    nxt_fd_t         fd[2];     /* up to 2 descriptors via SCM_RIGHTS */
    nxt_port_msg_t   port_msg;  /* header */
} nxt_port_send_msg_t;
```

**Header `nxt_port_msg_t`:**
```c
uint32_t    stream;      /* RPC request/response pairing */
nxt_pid_t   pid;         /* sender pid (unused on Linux — CMSG instead) */
uint32_t    reply_port;  /* where to reply */
uint8_t     type;        /* NEW_PORT, MMAP, DATA, READY, ... */
uint8_t     last, mmap, nf, mf;  /* fragmentation flags */
```

**Key: fd via SCM_RIGHTS.** A message carries up to 2 descriptors (socket,
memfd, queue). Ownership semantics are what PR #208-#212 harden.

### 2. Large data — shared memory (mmap)

`nxt_port_mmap_header_t` — large payloads (request bodies, config):

```
sender:   ftruncate(memfd, size) → mmap → write → MMAP message
receiver: gets fd (memfd) → fstat → mmap → read
```

Shared segment (`nxt_port_memory.c`) with chunks — the router↔worker data
path.

## Port lifecycle

### 1. Creation (NEW_PORT)

```
process A (e.g. prototype) creates socketpair:
  pair[0] — own end
  pair[1] — handed over via SCM_RIGHTS in NEW_PORT message
  + queue_fd (memfd queue)

→ B (router) receives NEW_PORT:
  nxt_port_new_port_handler():
    msg->fd[0] = pair[1]  → port->pair[1]
    msg->fd[1] = queue_fd → mmap'd as port->queue
```

### 2. Send

```
nxt_port_socket_write():
  if data ≤ max_size   → SOCK_DGRAM sendmsg
  if data > max_size   → mmap chunk + MMAP message
  fragmentation: mf/nf bits for large buffers
```

### 3. Receive

```
nxt_port_read_handler() → nxt_port_read_msg_process():
  recvmsg() → nxt_port_recv_msg_t
  cmsg_pid — kernel-validated sender PID (SCM_CREDENTIALS)
  → dispatch by msg->port_msg.type → handler
```

## Queue (nxt_port_queue_t)

Ring queue in shared memory (memfd):

```c
nxt_port_queue_t (655380 bytes):
  header: producer/consumer indices, magic
  buffer: ring of messages
```

Producer writes, consumer reads — both via mmap on the same memfd. Primary
router↔worker path. #211 validates the object size before mapping.

## RPC layer (nxt_port_rpc.c)

Streams pair requests with responses:

```
nxt_port_rpc_register_peer() → stream N
request  with stream=N
response with stream=N → matches pending callback
```

## Security boundary (what #208-#212 fix)

| Vector | Mechanism | PR |
|--------|-----------|-----|
| Sender pid | **cmsg_pid** (SCM_CREDENTIALS, kernel-validated) | — |
| Forged WHOAMI | handler closed 1 of 2 fds | #208 |
| Forged PROCESS_READY | queue remap, state corruption | #208 |
| Forged CHANGE_FILE | NULL deref + OOB read | #210 |
| Short memfd | SIGBUS on access | #211 |
| Forged NEW_PORT | stack-garbage pointer + re-point vuln | #212 |
| fd exhaustion | forged messages leak fds | #208, #212 |

### Trust model

- Message **type** comes off the wire — any peer can name any type.
- PID is kernel-validated (cmsg), but pid-isolated workers report a
  namespace-local pid — PROCESS_READY lookup stays on self-declared pid
  (documented limitation in #208).
- Handlers must call `nxt_port_recv_msg_close_fds()` on reject paths —
  the dispatcher does not reclaim fds after the handler returns.

## Performance

From connection-flow-visualization: IPC router↔worker is **<0.1% of
request time** (~20-200µs small, ~20µs response). UDS + shared memory is
faster than FastCGI sockets. Main path:

```
recv TCP (50µs) → parse (200µs) → route (10µs) → IPC (20-200µs)
→ PHP handler (45ms!) → IPC back (20µs) → writev (50µs)
```

## Known gaps / open items

- SO_REUSEADDR used for listeners (restart); SO_REUSEPORT not used
  (zero-downtime router restart would need it — separate feature).
- #212 respawn interaction: NEW_PORT for an existing port is now refused;
  respawn flow (kill -9 worker → new prototype sends NEW_PORT while the
  old port record is still live) needs the owner-state check (STARTING vs
  active) before refusing.
- `nxt_app_new_port_handler()` closes fds right after the base handler —
  correct for discovery/prototype (they don't map queues), but the
  respawn path must not lose the queue fd.
