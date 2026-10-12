---
title: "FreeUnit v1 Architecture"
description: "FreeUnit v1 architecture — multi-process C server on event loop"
tags: [freeunit, v1, architecture, c, processes, event-loop, libunit]
---

# FreeUnit v1 Architecture

## Process model

FreeUnit (like NGINX Unit) uses a multi-process architecture:

```
┌──────────────────────────────────────────────────────┐
│                 nxt_main_process                      │
│  (master — root, config, lifecycle)                   │
└──────────────────────┬───────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────────┐ ┌─────────┐ ┌─────────────────┐
│   nxt_controller │ │ router  │ │   app workers   │
│  (REST API,      │ │ (HTTP   │ │  (PHP/Python/   │
│   control)       │ │  proxy) │ │   Ruby/... per  │
└─────────────────┘ └─────────┘ └─────────────────┘
```

### Processes (C, event-driven)

| Process | File | Role |
|---------|------|------|
| **Master** | `nxt_main_process.c` | root-owned, parses config, forks processes |
| **Controller** | `nxt_controller.c` | REST API (JSON), application management |
| **Router** | `nxt_router.c` (5974 lines) | HTTP proxy, load balancing, routing |
| **App workers** | `nxt_php_sapi.c` etc. | per-language processes |

### IPC: Port and Shared Memory

- **Port** (`nxt_port.c`, `nxt_port.h`): main IPC primitive
  - `nxt_port_socket.c` — message passing via Unix sockets
  - `nxt_port_memory.c` — shared memory for large payloads
  - `nxt_port_rpc.c` — RPC mechanism between processes
  - `nxt_port_queue.h` — queue-based messaging (stack overflow protection #88)
- **libunit** (`nxt_unit.c`, 6800 lines): client library for app workers
  - Registration, send/receive requests
  - Shared memory mmap

### Event Engine

- `nxt_event_engine.c` / `nxt_event_engine.h` — event loop abstraction
- `nxt_epoll_engine.c` — Linux epoll implementation
- `nxt_kqueue_engine.c` — macOS/FreeBSD kqueue
- Support: epoll, kqueue, poll, select

### HTTP

- `nxt_h1proto.c` (3110 lines) — HTTP/1.1 protocol (only one)
- HTTP/2 — in roadmap (D2, ~3 months)
- WebSocket: `nxt_h1proto_websocket.c`, `nxt_http_websocket.c`
- Proxy: `nxt_http_proxy.c`
- Routing: `nxt_http_route.c`, `nxt_http_route_addr.c`
- Headers: `nxt_http_set_headers.c` (control char protection #90)

### Conn (Connection)

- `nxt_conn.c` / `nxt_conn.h` — connections
- `nxt_conn_accept.c` — accept new connections
- `nxt_conn_close.c` — close
- `nxt_conn_write.c` — write path (half-close fix PR#54)

### Security and Isolation

- `nxt_isolation.c` (1148 lines) — cgroups, capabilities, rootfs
- `nxt_cgroup.c` — cgroup v2 management
- `nxt_capability.c` — Linux capabilities
- `nxt_fs_mount.c` — mount namespaces (openat2 #115)
- TLS: `nxt_openssl.c` (OCSP stapling — issue #6)
- SCM_CREDENTIALS: `nxt_port_socket.c` — IPC sender auth (#91)

### Language Bindings (SAPI)

| Language | File | Lines |
|----------|------|-------|
| PHP | `nxt_php_sapi.c` | 2653 |
| Python WSGI | `nxt_python_wsgi.c` | — |
| Python ASGI | `nxt_python_asgi_lifespan.c`, `nxt_python_asgi_websocket.c` | — |
| Ruby | `nxt_ruby.c`, `nxt_ruby_stream_io.c` | 63+140 |
| Perl | `nxt_perl_psgi.c` | — |
| Java | `nxt_jni_*.c` (14 files) | — |
| Node.js | `nxt_napi.h` | — |
| WASM | `nxt_wasm.c` (156 lines in pre-1.35.6) | — |

### Build System

- `auto/` — autoconf-style configure (NGINX heritage)
- `auto/cc/` — compiler-specific flags
- `auto/modules/` — modules
- `auto/os/` — OS-specific
