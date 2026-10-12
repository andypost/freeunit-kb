---
title: "FreeUnit v2 - Liveness Monitor"
description: "Hung detection mechanism via TGID invariant"
tags: [freeunit, v2, liveness, tgid, proc, pidfd, health-ping]
---

# FreeUnit v2 Liveness Monitor

## TGID invariant (core of liveness)

On Linux, PID from Command::spawn() == TID of its thread group leader.
/proc/<pid>/task/<pid>/stat — always stat of the leader.

**Contract section 3:** worker userland executes on thread group leader.
No background threads from userland (pthread_create, pcntl_fork after start).

**Check B6:** startup-check: getmypid() == spawn_pid.
If mismatch — worker rejected from pool.

### Why not /proc/<pid>/stat?

/proc/<pid>/stat counts CPU-time of ALL process threads.
If worker violates contract and creates pthread, a noisy thread masks
hung of the main thread. Polling task/<pid>/stat reads ONLY the leader.

## Three-phase detection

### Phase 1: Polling (every 100ms)
- utime + stime from /proc/<pid>/task/<pid>/stat
- State (R/S/D/Z) from /proc/<pid>/task/<pid>/status

### Phase 2: Suspicion
Conditions:
- request_active = 1
- utime + stime not growing for 200ms (2 measurements)
- State = S (sleeping) or D (uninterruptible)

Both (A) true hang on syscall and (B) honest async-await look
identical from /proc: CPU flat, state S.

### Phase 3: Verification (Health-Ping)
- Rust sends PING_LIVENESS via UDS
- Waits PONG_LIVENESS with 50ms timeout
- Ping handled by worker UDS adapter (Revolt), transparent to app code

**Result:**
- **Timeout (50ms):** true hung -> SIGKILL + respawn (<=250ms)
- **PONG received:** event loop alive, worker waiting on upstream

## Request Watchdog

| Scenario | CPU-time | Action |
|----------|----------|--------|
| Request > exec_ttl, CPU flat | Flat | Liveness -> SIGKILL |
| Request > exec_ttl, CPU rising | Rising | slow_requests++ -> draining -> restart |
| Request < exec_ttl | - | Normal processing |

## B5: Multithread regression test

Separate parasite process (same uid) burning CPU in a loop.
Worker main thread blocked on mysqli.
Liveness detects hung via task/<pid>/stat (leader CPU flat + D state),
despite noise neighbor. SIGKILL in <=200ms.

Test covers regression: polling using TGID vs /proc/<pid>/stat counting all threads.
