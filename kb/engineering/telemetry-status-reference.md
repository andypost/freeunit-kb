# FreeUnit Telemetry & Status — Read & Configure

## 1. What You Can Read (Observability Surfaces)

### 1.1 Control API: GET /status

```
GET /status                      → router-level stats
GET /status/connections/<id>     → per-connection stats
GET /status/applications/<name>  → per-app stats
```

**Router-level response (nxt_router_status_handler, src/nxt_router.c:955):**

```json
{
  "accepted_conns": 1234567,
  "idle_conns": 48,
  "closed_conns": 1234519,
  "active_conns": 89,
  "requests": 5432100,
  "applications": {
    "drupal": {
      "processes": 8,
      "idle_processes": 3,
      "active_requests": 5,
      "pending_processes": 0
    }
  }
}
```

**Field meanings:**

| Field | Source | Meaning |
|-------|--------|---------|
| `accepted_conns` | `engine->accepted_conns_cnt` | Total accepts since start (monotonic) |
| `idle_conns` | `engine->idle_conns_cnt` | Keep-alive connections waiting for next request |
| `active_conns` | Calculated | Connections currently being processed |
| `closed_conns` | `engine->closed_conns_cnt` | Total closed since start |
| `requests` | `engine->requests_cnt` | Total HTTP requests since start |
| `processes` | `app->processes` | Configured worker count |
| `idle_processes` | `app->idle_processes` | Workers waiting for requests |
| `active_requests` | `app->active_requests` | Currently executing in workers |
| `pending_processes` | `app->pending_processes` | Starting up (not yet ready) |

**Quick health check:**
```
OK:   idle_processes > 0                → room to accept
WARN: idle_processes = 0, active < max  → fully loaded
CRIT: idle_processes = 0, active = max  → queue building, will 503
```

### 1.2 Control API: GET /config

Returns the full active configuration as JSON:
```
GET /config
→ { "listeners": {...}, "applications": {...}, "access_log": "..." }
```

### 1.3 Access Log

```json
{
  "access_log": {
    "path": "/var/log/unit/access.log",
    "format": "$remote_addr - $time_local \"$request\" $status $body_bytes_sent"
  }
}
```

Pre-defined format or custom template. No stdout/stderr — file-only.

### 1.4 Error Log

Not controllable via Control API. Configured at unit start:
```
unitd --log /var/log/unit/error.log
```
Errors write through `nxt_log()` → `nxt_log_file_handler()` → append to file.
Levels: `alert`, `error`, `warn`, `info`, `debug`.

### 1.5 OpenTelemetry Spans

**What's exported (to OTLP collector):**

For every HTTP request, one span with:
- `http.method` = GET/POST/...
- `http.scheme` = http/https
- `http.target` = /index.php?q=node/1
- `http.host` = example.com
- `http.status_code` = 200/404/500
- `http.route` = matched route pattern
- `net.host.name` = listener host
- `net.host.port` = listener port
- `net.peer.ip` / `net.peer.port` = client address

Plus for PHP:
- `app.type` = "php"
- `app.version` = "8.5.7"

**Span lifecycle:**

```
Request received:
  → nxt_otel_start_span("HTTP GET")
  → set attributes from parsed headers
  → check W3C traceparent (inherit or restart)

Request during processing:
  → span stays open
  → worker events: request_start, processing

Response ready:
  → nxt_otel_set_status(200)
  → nxt_otel_end_span()
  → export via batch span processor
  → OTLP/HTTP (POST /v1/traces) or OTLP/gRPC

Connection close:
  → span already exported (no connection tracking in span)
```

**What you DON'T get:**
- ❌ No per-worker metrics (no worker_id in span)
- ❌ No DB query spans (no PHP extension integration)
- ❌ No response body metrics
- ❌ No TCP/TLS handshake timing

### 1.6 cgroup stats (per-worker, Linux only)

Worker process isolation: cgroup files readable at runtime.

```
/sys/fs/cgroup/freeunit/drupal/worker-3/
  ├─ memory.current       → RSS in bytes
  ├─ memory.max           → configured limit
  ├─ cpu.stat             → usage_usec, user_usec, system_usec
  ├─ pids.current         → threads in this worker
  └─ cgroup.procs         → pids in this cgroup
```

Accessible from host or container (with capabilities), not via Unit API directly.

---

## 2. What You Can Configure (Control Surface)

### 2.1 PUT /config — Full Config Replace

```
PUT /config
{
  "listeners": {...},
  "applications": {...},
  "access_log": "...",
  "settings": {
    "telemetry": {
      "service_name": "FreeUnit",
      "protocol": "http",
      "endpoint": "http://otel-collector:4318/v1/traces",
      "batch_size": 512,
      "sampling_ratio": 0.1
    }
  }
}
```

### 2.2 POST /control/applications/<name>/restart

Graceful restart of all workers for an app:
```
POST /control/applications/drupal/restart
→ spawns new workers, drains old ones
→ zero-downtime: old workers finish in-flight requests, new ones take new
→ not a full /config reload (only one app, no listener changes)
```

### 2.3 GET /control/certificates

```
GET /control/certificates
→ lists loaded TLS certificates (names, not contents)
```

### 2.4 PUT /control/certificates/<name>

Upload/update TLS bundle:
```
PUT /control/certificates/example
{
  "cert": "-----BEGIN CERTIFICATE-----...",
  "key": "-----BEGIN PRIVATE KEY-----..."
}
→ validates key matches cert at upload time (1.36.0+)
```

---

## 3. Telemetry Configuration Reference

```json
{
  "settings": {
    "telemetry": {
      "service_name": "FreeUnit",           // default: "FreeUnit" (was "NGINX Unit")
      "protocol": "http",                   // "http" (OTLP/HTTP) or "grpc" (OTLP/gRPC)
      "endpoint": "http://localhost:4318",  // collector address
                                             // HTTP: POST /v1/traces
                                             // gRPC: tonic over h2c (plaintext only)
      "batch_size": 512,                    // spans per batch (1-65536)
      "sampling_ratio": 0.1,               // 0.0 = none, 1.0 = all (0-1)
      "export_timeout_millis": 10000        // timeout for collector connection
    }
  }
}
```

**Defaults and constraints:**

| Param | Default | Min | Max | Note |
|-------|---------|-----|-----|------|
| service_name | "FreeUnit" | — | — | Must be non-empty |
| protocol | "http" | — | — | "http" or "grpc" |
| batch_size | 512 | 1 | 65536 | Invalid values: error at config load (1.36.0+) |
| sampling_ratio | 1.0 | 0 | 1 | ParentBased sampler — remote parent flags honoured (1.36.0+) |
| export_timeout_millis | 10000 | — | — | Connection timeout to collector |

**Build flag:** `--otel` required at configure time. Both HTTP and gRPC transports compiled in.

---

## 4. Prometheus /metrics (Roadmap X8, NOT shipped)

Not yet implemented. Planned: X8 in roadmap.

```
GET /metrics   # → Planned for month 6
  # HELP freeunit_connections_accepted_total Total accepted connections
  # TYPE freeunit_connections_accepted_total counter
  freeunit_connections_accepted_total 1234567

  # HELP freeunit_requests_total Total requests
  # TYPE freeunit_requests_total counter
  freeunit_requests_total{app="drupal"} 5421000

  # HELP freeunit_worker_active Current active workers
  # TYPE freeunit_worker_active gauge
  freeunit_worker_active{app="drupal"} 5

  # HELP freeunit_worker_idle Current idle workers
  # TYPE freeunit_worker_idle gauge
  freeunit_worker_idle{app="drupal"} 3
```

---

## 5. Health Check Endpoints (Application-Level)

Unit apps can expose health checks as normal HTTP routes:

```json
{
  "listeners": {
    "*:8080": {
      "pass": "routes/main"
    }
  },
  "routes": {
    "main": [
      {
        "match": { "uri": "/health" },
        "action": { "return": 200 }
      },
      {
        "action": { "pass": "applications/drupal" }
      }
    ]
  }
}
```

Plan: `/status/applications/<name>/php` (roadmap P2) — opcache stats, JIT state, request counters.

---

## 6. Live Debug Flow

```
What's happening right now?

1. GET /status                                     ← top-level: connections, apps
2. GET /status/connections                         ← per-connection: who's connected
3. GET /status/applications/drupal                 ← drupal: workers, queue
4. ps aux | grep unit                              ← OS level: pids, RSS, CPU
5. cat /sys/fs/cgroup/freeunit/drupal/*/cpu.stat    ← cgroup: per-worker CPU
6. cat /sys/fs/cgroup/freeunit/drupal/*/memory.current  ← cgroup: per-worker RAM
7. OTLP collector dashboard                        ← spans: latency, errors, sampling
8. Access log tail -f                              ← request log: timing, status codes

Typical incident flow:
  /status → active = max, idle = 0 → all workers busy
  Check OTLP spans → DB queries taking 5s (not Unit's fault)
  Check access log → 502 errors from upstream timeout
  Decision: increase processes or fix the DB
```

---

## 7. Comparison: What you can see now vs roadmap

| Feature | Now | Planned | When |
|---------|-----|---------|------|
| Router-level stats | ✅ GET /status | — | — |
| Connection-level stats | ✅ GET /status/connections | — | — |
| Per-app worker stats | ✅ processes/idle/active | — | — |
| Access logs | ✅ File | ✅ Structured JSON (D8) | Month 2 |
| Error logs | ✅ File (--log) | ✅ Same (stable) | — |
| OTLP spans | ✅ HTTP+gRPC 0.32 | — | — |
| Prometheus /metrics | ❌ | ✅ X8 | Month 6 |
| PHP opcache stats | ❌ | ✅ P2 (Status API) | Month 2 |
| Per-worker CPU/RAM (API) | ❌ (cgroup files only) | ✅ P2 extension | Month 2 |
| Graceful reload | ❌ | ✅ X3 | Month 2 |
| Structured logs | ❌ | ✅ D8 | Month 2 |
| Request-level timing | ❌ (only spans) | ✅ Span annotations | Month 6 |
