---
title: "FreeUnit v2 - KPIs and DoD"
description: "PoC success criteria and Definition of Done"
tags: [freeunit, v2, kpi, testing, poc]
status: "PoC - all KPIs met"
---

# FreeUnit v2 KPIs and Definition of Done

PoC considered successful on 4 vCPU / 8 GB RAM:

## Throughput
Pool of 4 NTS workers, mixed load (50% async I/O, 50% CPU-bound: 1MB JSON parse).
RPS + latency (p50/p99/p99.9) >= PHP-FPM + FreeUnit v1.

## Memory Efficiency
Pool RAM under high concurrency does not grow linearly.
>= 3-5x better than FPM.

## Blast Radius
On hang: loss <= 30 requests (semaphore size).
detect to respawn < 500 ms.

## False-Positive Rate
< 0.01% on test suite B1-B6.

## Tests (B1-B6)

| Test | Scenario | Expectation |
|------|----------|-------------|
| B1 | sleep(2) in userland | SIGKILL in <=250ms |
| B2 | json_decode 10MB (~500ms CPU) | Do NOT kill, normal completion |
| B3 | CPU-bound + checkpoints | Out-of-scope PoC |
| B4 | Mixed: 1000 req, 1% sleep(5) | 10 workers killed+respawn, rest alive, p99 degradation < 50ms |
| B5 | Multithread regression (noisy neighbor) | SIGKILL in <=200ms |
| B6 | TGID sanity: getmypid() == spawn_pid | Startup-check, reject on violation |

## PoC Status: COMPLETE (2026-06-15)

- 38/38 issues closed
- 76 tests green (+1 release-bench under #[ignore])
- H1-H6 hypotheses proven on PHP 8.5.7 NTS
- PoC development stopped
