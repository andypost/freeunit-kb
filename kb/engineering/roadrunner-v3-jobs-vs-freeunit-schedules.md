---
title: RoadRunner v3.0.0 `jobs` vs FreeUnit `schedules` — a queue is not a cron
description: Why RoadRunner's "jobs" plugin and FreeUnit's planned `schedules` solve different problems (broker-fed queue vs in-process timer); the three axes where v3.0.0's jobs does touch the FreeUnit plan (named worker pools, outcome metrics, trace continuity); and everything else RoadRunner v3.0.0 shipped.
tags: [roadrunner, jobs, schedules, cron, queue, compare, pr452]
status: analysis
updated: 2026-10-09
resources:
  - https://github.com/roadrunner-server/roadrunner/releases/tag/v3.0.0
  - https://github.com/freeunitorg/freeunit/pull/452
  - https://github.com/freeunitorg/freeunit/issues/443
---

# RoadRunner v3.0.0 `jobs` vs FreeUnit `schedules` — a queue is not a cron

**Created:** 2026-10-09 by SOUL. Sources: the RoadRunner v3.0.0 release notes
(published 2026-10-08) and FreeUnit PR #452 / epic #443.

## TL;DR

They are **different axes**, so a head-to-head "implementation" comparison is
wrong. RoadRunner `jobs` is an **event-driven queue consumer** (jobs arrive from
an external broker). FreeUnit `schedules` is a **time-driven in-process timer**
(the server itself fires periodic internal requests into an app). RoadRunner
v3.0.0 has **no scheduler at all** — `cron`, `scheduler`, `timer` and
`time-based` appear **zero** times in its release notes. The thing FreeUnit's
`schedules` competes with (a cron with no sidecar) RoadRunner does not ship.

## RoadRunner `jobs` = queue/consumer

- Source = **external broker**: AMQP, SQS, Kafka, NATS, **NSQ (new in v3)**,
  Redis, Beanstalk, memory.
- A PHP worker pool **consumes** jobs; delivery is at-least-once with
  retry / requeue / dead-letter semantics.
- Concurrency = pool size. The `jobs` plugin in v3.0.0 adds **named worker
  pools** (a pipeline gets its own PHP pool, selected by a `pool` header),
  **trace continuity** (producer trace context preserved on RPC submit) and
  **outcome metrics** (success/failed/**requeued** counted separately,
  `rr_jobs_jobs_requeue`).
- RoadRunner's *cron* is a separate community plugin that spawns a shell command
  per tick (a cold PHP each time) — the comparator FreeUnit's plan names. It is
  **not** part of the `jobs` plugin and **not** in v3.0.0's notes.

## FreeUnit `schedules` = timer (PR #452, target 1.38.0)

- New top-level `"schedules"` object; FreeUnit sends **periodic internal
  requests** into an application — cron-like, **no client and no sidecar**.
- Config per schedule: `pass`, `uri`, `interval`, `jitter`, `timeout`,
  `overlap: skip`, `headers`. Validated by building the same request a run uses.
- A run is a normal application request: it counts in `/status`, goes through
  `limits` and the app queue, and is written to the access log; an OTel span is
  created with telemetry on.
- `/status/schedules` shows per-schedule counters; a timed-out run records
  `last_status` 503 and the worker keeps its slot in `processes.max`.

## Where the two touch (and still differ)

| Theme | RoadRunner `jobs` v3 | FreeUnit `schedules` |
|---|---|---|
| Trigger | broker message | time (`interval`/`jitter`) |
| Source | external broker | the server itself |
| Isolation | **named worker pools** (pipeline → its own PHP pool, by `pool` header) | capacity separation **by application** (a second app, `processes: 1`, idle-reaper-exempt) |
| Metrics | success/failed/**requeued** | `/status/schedules` counters + `last_status` |
| Tracing | producer trace continuity on submit | OTel span per run |
| Rescheduling | queue (retry/requeue/DLQ) | cron + `overlap: skip` |

The nearest RR analogue to the FreeUnit plan's "isolate jobs from traffic" is
**named worker pools** — but RR separates *queues* into pools, while FreeUnit
must separate by *application* because PHP targets share one app's processes.

## Everything else in RoadRunner v3.0.0 (context)

- **Core:** Go module `/v3`; Plugin API v6 (protobuf, `log/slog`, `pool/v2`,
  `goridge/v4`); Unix-socket attrs (mode/owner/group); `envfile` without
  experimental; **Goridge v4 drops MessagePack** (JSON/protobuf/Gob/raw remain);
  worker auto-scaling (`dynamic_allocator.max_workers`); default plugins add
  **NSQ, HTTP rate limiting, Zstd, protoreg**.
- **`http`:** middleware order left→right; **cleartext HTTP/2 (H2C prior
  knowledge; `Upgrade: h2c` removed)**; **PROXY protocol** v1/v2.
- **Middleware:** `rate_limiter` (global/IP/header, 429 + `Retry-After`),
  `zstd`, `static` (cache TTLs/limits, `rr reset static`), `proxy_ip_parser`
  trusted headers.
- **`grpc`:** server reflection, `google.rpc.Status` error details.
  **`otel`:** span-timing fix, **Zipkin exporter removed** (OTLP only).
- **`logger`:** Go `slog`; **`lock`:** Redis backend; **`redis`:** Sentinel auth;
  **`status`:** k8s `/livez`/`/readyz`; **`temporal`:** heartbeat/dynamic
  workflows; **`velox`:** modular build.
- **Queue drivers:** amqp (named connections, declaration controls), nats
  (retention, `ack_wait`), kafka (requeue isolation — a retry is not
  republished to the source topic), sqs (FIFO retry), beanstalk (headers).

## Verdict for FreeUnit

RR `jobs` is **not a competitor to `schedules`** — one is a queue, the other a
cron. The overlap is only **pool isolation** and **metrics/tracing**. The
"scheduler without a sidecar" that `schedules` (#452) delivers, RoadRunner
v3.0.0 does not offer. Useful as a design reference for #452 on two points:
named worker pools (isolation by pipeline) and per-attempt outcome metrics.

Related: `octane-roadrunner-frankenphp-research.md` (persistent-worker
landscape), `scheduled-tasks-plan.md`, `scheduled-tasks-app.md`.
