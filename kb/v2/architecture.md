---
title: "FreeUnit v2 PoC - Architecture"
description: "Rust orchestrator + persistent NTS PHP worker pool"
tags: [freeunit, v2, rust, php, nts, poc, revolt, ipc, uds]
status: "PoC complete (2026-06-15)"
---

# FreeUnit v2 Architecture

## High-level

``'
+-------------+     UDS (binary framing)     +--------------+
| Rust Master +----------------------------->+ PHP Worker 1 |
| (tokio)     |<-----------------------------+ (NTS, Revolt)|
|             |     SCM_RIGHTS / pipes       +--------------+
| - epoll     |                              | PHP Worker 2 |
| - TLS       |                              +--------------+
| - routing   |                              | ...          |
| - lifecycle |                              +--------------+
| - liveness  |
+-------------+
``'

## IPC Layer

- Unix Domain Sockets (UDS) with binary framing (length-prefix)
- Large payloads: SCM_RIGHTS (fd passing) or pipes
- MAX_FRAME_LEN protection against OOM
- recv_fd rejects MSG_CTRUNC (fd-confusion protection)
- Partial send: retry loop on writability

## Liveness Monitor (section 4)

Three-phase mechanism distinguishing hung from slow:

1. **Polling** (every 100ms): /proc/<pid>/task/<pid>/stat - CPU-time thread group leader
2. **Suspicion**: CPU-time not growing 200ms + state S/D + request_active=1
3. **Verification**: PING_LIVENESS via UDS, PONG_LIVENESS in 50ms

## TGID invariant

PID from Command::spawn() == TID of thread group leader.
Worker runs on TGID. No background threads.

## Backpressure

- tokio::sync::Semaphore (30 permits/worker)
- Power of Two Choices load balancing
- Both busy -> 503

## Graceful Crash Recovery

- pidfd detects UDS break/process death
- Log, cleanup, respawn, 502
