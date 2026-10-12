# Laravel Octane / RoadRunner / FrankenPHP — Research for FreeUnit SAPI

**Created:** 2026-07-13
**Goal:** Understand how Octane/RoadRunner/FrankenPHP work, how FreeUnit's
roadmap P4 (persistent worker) compares, and how to position FreeUnit for
the Laravel ecosystem.

---

## 1. The Problem These Projects Solve

Standard PHP (PHP-FPM) does a **cold bootstrap on every request**:

```
Request → FPM worker → MINIT → RINIT → load composer autoload →
  boot framework (Laravel kernel) → handle request → RSHUTDOWN → MSHUTDOWN
```

For Laravel, this bootstrap is **30-80ms** of pure overhead on every request.
The framework kernel, service providers, config, routes — all rebuilt from
scratch. On a 100ms request, 50ms is just booting Laravel.

**Persistent worker** model: boot the framework ONCE, then feed it requests
without re-booting:

```
Process start → MINIT → RINIT → boot Laravel → [READY]
Request 1 → [framework already booted] → handle → keep alive
Request 2 → [framework still booted] → handle → keep alive
...
```

**Result: 2-5x throughput improvement** on real Laravel apps.

---

## 2. The Three Competitors

### 2.1 Laravel Octane (orchestration layer)

**What it is:** Laravel's official high-performance engine. NOT a standalone
server — it's an **adapter layer** that sits between Laravel and one of two
backend servers.

**Architecture:**
```
Laravel Application
       │
Laravel Octane (adapter)
       │
       ├── Swoole backend (C extension, event loop, coroutines)
       └── RoadRunner backend (Go process, FastCGI-like protocol)
```

**Key components:**
- `Octane::route()` — registers routes outside the HTTP kernel
- `Octane::tick()` — periodic timers (Swoole only)
- `Octane::concurrent()` — parallel execution (Swoole only)
- `Octane::fork()` — process forking (Swoole only)
- Between-request state reset: `FlushTemporaryState` listener

**State management (the hard part):**
- Static properties, singletons, container instances must be reset between requests
- Octane provides `ResetState` interface — services implement `reset()`
- Laravel's core services (config, router, view, etc.) are pre-registered with Octane
- User code must register custom state via `Octane::resetState()`

**Concurrency:**
- Swoole backend: coroutines (true concurrency, cooperative multitcheduling)
- RoadRunner backend: serial (one request at a time per worker)

**Limitation:** Swoole backend requires a PHP with the Swoole C extension.
RoadRunner backend requires a Go binary.

---

### 2.2 RoadRunner (application server)

**What it is:** A high-performance PHP application server written in **Go**.
Manages PHP worker pools, terminates HTTP, load-balances.

**Architecture:**
```
HTTP Client → RoadRunner (Go process)
                 │
                 ├── HTTP/1.1 + HTTP/2 termination
                 ├── TLS termination
                 ├── Load balancer (round-robin)
                 ├── Worker pool manager
                 │      ├── PHP worker 1 (FastCGI-like IPC)
                 │      ├── PHP worker 2
                 │      └── PHP worker N
                 │
                 └── Static file serving
```

**Worker communication:**
- PHP workers communicate with RoadRunner via **internal JSON protocol** over
  pipes (not FastCGI, not HTTP)
- Each worker is a PHP-CLI process running RoadRunner's `Worker.php`
- Protocol: JSON request (method, path, headers, body) → JSON response

**Worker lifecycle:**
```php
// RoadRunner worker.php
while ($req = $worker->waitRequest()) {
    $response = $kernel->handle($req);  // Laravel already booted
    $worker->respond($response);
    // Worker stays alive, waiting for next request
}
```

**Key features:**
- HTTP/2 support (Go's net/http)
- gRPC support (Go-native)
- Static file serving (Go, highly efficient)
- Queue workers (built-in, no need for Laravel Horizon/Supervisor)
- Metrics endpoint (Prometheus)
- Hot reload (file watcher → worker respawn)
- Plugin system: PHP, static, gzip, headers, status, health

**Limitations:**
- Go binary dependency (~20MB)
- PHP runs as CLI, not embedded SAPI — has IPC overhead
- JSON protocol means serialization/deserialization per request
- No connection pooling to databases (each worker has its own PDO)
- Swoole is better for coroutine-based concurrency

---

### 2.3 FrankenPHP (embedded SAPI)

**What it is:** A modern PHP application server built on **Caddy** (Go web server)
with PHP **embedded** as a C library via a custom SAPI. Created by Kévin Dunglas.

**Architecture:**
```
HTTP Client → Caddy (Go web server)
                 │
                 ├── HTTP/1.1, HTTP/2, HTTP/3 (QUIC)
                 ├── TLS (automatic HTTPS via Let's Encrypt)
                 ├── Reverse proxy
                 ├── Static file serving
                 │
                 └── FrankenPHP module (Go → C SAPI)
                          │
                          ├── Worker mode (persistent)
                          │      ├── PHP worker 1 (embedded libphp)
                          │      ├── PHP worker 2
                          │      └── PHP worker N
                          │
                          └── Traditional mode (one-shot per request)
```

**Worker mode (the key innovation):**
```php
// FrankenPHP worker-mode script
while ($request = frankenphp_handle_request()) {
    // $request is a standard Symfony HttpFoundation Request
    $response = $kernel->handle($request);
    $response->send();
    $kernel->terminate($request, $response);
}
// Framework (Laravel/Symfony) bootstrapped ONCE before the loop
```

**Key innovation:** `frankenphp_handle_request()` — a PHP function that:
1. Suspends the PHP runtime (using Fibers internally)
2. Waits for the next HTTP request from Caddy
3. Resumes the runtime with a new request context
4. Returns `true` when a request is available, `false` when shutting down

**Between-request state reset:**
- FrankenPHP resets `$_SERVER`, `$_GET`, `$_POST`, `$_COOKIE`, `$_FILES`,
  `$_ENV`, php://input, request body
- User code responsible for resetting static properties, singletons
- Provides `request_terminated` event hook

**Concurrency model:**
- Multiple PHP threads (ZTS) in one Caddy process (Go runtime cooperates)
- Each thread runs its own `while ($request = frankenphp_handle_request())` loop
- Requests within one thread are serial; across threads are parallel

**Key features:**
- HTTP/3 support (via Caddy)
- Automatic HTTPS
- Compression (br/gzip)
- Reverse proxy
- Real-time metrics
- Early Hints (103)
- Docker-friendly single-container

**Limitations:**
- Requires ZTS PHP (thread-safe build) for worker mode
- Caddy dependency (Go binary, ~30MB)
- Complex build (Go + C + PHP)
- Early-stage, some edge cases with non-thread-safe extensions
- Go GC pauses can affect PHP workers (debatable)

---

## 3. FreeUnit P4: The Best of Both Worlds

FreeUnit's roadmap already identifies the winning architecture. Here's how P4
maps against the competitors:

### FreeUnit P4 (Persistent Worker Mode)

From `roadmap/unit-php.md`:
> Config: `"worker": "/path/to/worker.php"`. Script runs once, then a callback
> (set via a Unit-provided PHP extension function) is invoked per request with
> `$request`, returning `$response`. No re-init between requests.
> Different from TrueAsync: serial, not coroutine-based — works with any PHP
> 8.1+, no TrueAsync API needed. Stackable with P1 threads.

**Architecture:**
```
HTTP Client → FreeUnit C-core (epoll/io_uring)
                 │
                 ├── HTTP/1.1 termination
                 ├── TLS termination (OpenSSL)
                 ├── Router (route matching, static files)
                 │
                 └── PHP SAPI (embedded libphp)
                          │
                          ├── Worker 1 (persistent, embedded)
                          │      ├── boot: composer autoload + Laravel kernel
                          │      ├── request 1 → kernel->handle() → respond
                          │      ├── request 2 → kernel->handle() → respond
                          │      └── ...
                          │
                          ├── Worker 2 (persistent, embedded)
                          └── Worker N
```

### Comparison Matrix

| Feature | RoadRunner | FrankenPHP | FreeUnit P4 |
|---------|-----------|------------|-------------|
| **Core language** | Go | Go + C | **C** |
| **PHP integration** | CLI + JSON IPC | Embedded SAPI (C) | **Embedded SAPI (C)** |
| **IPC overhead** | JSON serialization | None (shared memory) | **None (shared memory)** |
| **Binary size** | ~20MB (Go) | ~30MB (Caddy+Go) | **~5MB** |
| **Memory per worker** | ~30-50MB | ~20-40MB | **~15-30MB** |
| **HTTP/2** | ✅ (Go) | ✅ (Caddy) | ❌ (planned via Buran) |
| **HTTP/3** | ❌ | ✅ (Caddy) | ❌ (planned via Buran) |
| **TLS** | ✅ | ✅ (auto HTTPS) | ✅ (OpenSSL) |
| **ZTS required** | ❌ | ✅ (for worker mode) | ❌ (serial mode, P1 adds threads) |
| **Concurrency model** | Serial per worker | Threads per process | **Serial, then P1 threads** |
| **Octane support** | ✅ (native) | ✅ (native) | ❌ (needs adapter) |
| **Worker mode API** | JSON IPC | `frankenphp_handle_request()` | **`nxt_unit_request_loop_t`** (X4) |
| **State reset** | Manual | Auto + manual | **Auto + manual** |
| **io_uring** | ❌ | ❌ | ✅ (#30-31, RECV deferred) |
| **Kernel dispatch** | Go scheduler | Go scheduler | **SOCK_DGRAM (planned BWP)** |
| **Static files** | Go (efficient) | Caddy (efficient) | **C-core (zero-copy with io_uring)** |
| **Warm start** | Fast (CLI, no SAPI) | Fast (embedded) | **Fastest (embedded + persistent opcache)** |
| **Binary deps** | Go binary | Caddy + Go | **None** |

### Why FreeUnit P4 can win

1. **No Go binary.** RoadRunner and FrankenPHP both depend on Go. FreeUnit is
   pure C — smaller, faster, no Go GC pauses.

2. **No IPC overhead.** RoadRunner serializes requests to JSON. FrankenPHP and
   FreeUnit embed PHP directly — requests arrive as C structs in shared memory.

3. **io_uring.** Neither RoadRunner nor FrankenPHP uses io_uring. FreeUnit's
   POLL+ACCEPT tiers are done; RECV tier (zero-copy) is the projected win.

4. **Kernel-arbitrated dispatch (BWP).** Neither competitor uses kernel
   wake-one SOCK_DGRAM dispatch. This is a structural advantage under load.

5. **Config parity.** One `freeunit.yaml` works locally and in production. No
   Go binary to install, no Caddy to configure.

### What FreeUnit P4 is missing for Laravel

1. **Octane adapter.** Laravel Octane needs a backend driver. Currently ships
   with Swoole and RoadRunner backends. A `FreeUnitBackend` would make FreeUnit
   a first-class Octane citizen.

2. **Worker mode API.** The X4 contract (`nxt_unit_request_loop_t`) needs to
   land. Then a PHP-facing API like `freeunit_handle_request()` (similar to
   `frankenphp_handle_request()`) must be exposed.

3. **State reset.** Laravel's Octane state reset is well-documented. FreeUnit
   must replicate the same superglobals reset + provide a `resetState` hook.

---

## 4. Octane Backend Adapter Design for FreeUnit

### What Octane needs from a backend

Laravel Octane's `Worker` interface (simplified):
```php
interface Worker {
    public function handle(Request $request, RequestContext $context): Response;
}
```

The backend must:
1. Boot Laravel once (the `bootstrap.php` — app, kernel, config, routes)
2. Receive HTTP requests (method, URI, headers, body)
3. Map them to Symfony HttpFoundation `Request` objects
4. Call `$worker->handle($request, $context)`
5. Send the `Response` back
6. Reset state between requests
6. Support concurrent workers (multiple processes)

### Proposed FreeUnit Octane driver

```php
// freeunit-octane/Worker.php
namespace FreeUnit\Octane;

use Laravel\Octane\Workers\Worker;

class FreeUnitWorker
{
    private Worker $worker;
    private bool $booted = false;

    public function __construct()
    {
        // Boot Laravel ONCE — this is the persistent worker's main script
        $this->worker = Worker::create(
            basePath: base_path(),
            options: config('octane'),
        );
        $this->booted = true;
    }

    public function handle(): void
    {
        // FreeUnit SAPI persistent loop — similar to frankenphp_handle_request()
        while ($request = freeunit_handle_request()) {
            $symfonyRequest = SymfonyRequest::createFromFreeUnit($request);
            $response = $this->worker->handle($symfonyRequest, new RequestContext());
            freeunit_respond($response);
        }
    }
}
```

```php
// freeunit_handle_request() — provided by FreeUnit PHP extension
function freeunit_handle_request(): ?FreeUnitRequest
{
    // Internally calls X4's nxt_unit_request_loop_t
    // Blocks until a request arrives, returns request data
    // Returns null on shutdown
}
```

### What needs to land in FreeUnit for this

| Item | Roadmap | Effort | Status |
|------|---------|--------|--------|
| X4: Persistent-worker contract | Cross-cutting | ~3 weeks | Planned |
| P4: PHP persistent worker mode | PHP module | ~4-6 weeks | Planned |
| PHP extension: `freeunit_handle_request()` | PHP module | ~1 week | After X4 |
| Octane driver package | Community/Ecosystem | ~2-3 weeks | After P4 |
| State reset hooks | PHP module | ~1 week | Part of P4 |
| CI: Laravel Octane test suite | Testing | ~1 week | After driver |

**Total critical path:** X4 (3w) → P4 (4-6w) → PHP API (1w) → Octane driver (2-3w) = **~10-13 weeks**

---

## 5. Positioning FreeUnit for Laravel Community

### Key selling points for Laravel developers

1. **"Octane performance without Swoole or Go."**
   - Swoole: requires C extension, complex build, coroutine mental model
   - RoadRunner: requires Go binary, JSON IPC overhead
   - FreeUnit: pure C, embedded PHP, no extra dependencies

2. **"Your local dev IS production."**
   - One config, one binary, works everywhere
   - No Docker required for PHP layer
   - `freeunit.yaml` = same on laptop and server

3. **"Persistent workers with zero config."**
   - FrankenPHP requires Caddy + ZTS PHP build
   - FreeUnit works with NTS PHP (serial mode), ZTS optional (P1 threads)
   - Config: just set `"worker": "worker.php"`

4. **"The fastest static file serving."**
   - io_uring zero-copy `sendfile()` (RECV tier, projected)
   - No Go/Caddy in the path

5. **"Kernel-arbitrated PHP worker dispatch."**
   - Under load spikes: no FPM queue, no Go scheduler latency
   - SOCK_DGRAM wake-one (BWP)

### Messaging matrix

| Audience | Message |
|----------|---------|
| **Laravel developers** | "Octane-class performance, no Swoole, no Go. Just PHP." |
| **Agencies** | "One config for local + prod. Dynamic worktrees for branch-based dev." |
| **DevOps** | "Single C binary. No Docker for PHP. 5MB footprint. io_uring." |
| **Open-source community** | "Community fork of Nginx Unit. Apache 2.0. PHP 8.5-ready." |

### Community engagement plan

1. **FreeUnit Octane driver** — publish as `freeunit/octane-driver` package
2. **Benchmark blog post** — "FreeUnit vs FrankenPHP vs RoadRunner: Laravel Octane benchmarks"
3. **Laravel News / Laravel Daily** — pitch article about FreeUnit as Octane backend
4. **Laracon talk** — "Running Laravel on the edge: io_uring + embedded PHP"
5. **Laravel docs** — contribute installation guide
6. **Test suite** — CI matrix against major Laravel versions (10, 11, 12)

---

## 6. Technical Deep Dive: State Reset (the hard part)

The biggest challenge in any persistent worker is resetting PHP state between
requests. Here's how each project handles it:

### What must be reset

| State | Reset by | Mechanism |
|-------|----------|-----------|
| `$_SERVER`, `$_GET`, `$_POST`, etc. | Server (Octane/FreeUnit) | `$_SERVER = []` before each request |
| `php://input` | Server | Reopen stream |
| `ob_*` output buffers | Server | `ob_clean()` |
| Header state | Server | Reset `$response` object |
| Static properties | User code | `ResetState::reset()` |
| Singletons (container) | User code | Re-bind in container |
| Database connections | User code | Use `Octane::tick()` or context |
| File handles | User code | Close on `request_terminated` |
| Error handlers | User code | `restore_error_handler()` |
| Session | User code | `session_abort()` |

### FrankenPHP approach (reference for FreeUnit P4)

FrankenPHP resets between requests:
1. Superglobals (`$_SERVER`, `$_GET`, `$_POST`, `$_COOKIE`, `$_FILES`, `$_ENV`)
2. `php://input` stream
3. `INI runtime` values (per-request ini_set changes reverted)
4. Output buffering state

User code resets:
1. Static properties (via Octane's `resetState` list)
2. Laravel container singletons (Octane handles core services)
3. Custom state registered via `Octane::resetState()`

### FreeUnit P4 approach (proposed)

```c
// src/nxt_php_sapi.c — between requests in persistent mode
static void nxt_php_worker_request_reset(nxt_php_context_t *ctx) {
    // 1. Reset superglobals
    zend_hash_clean(Z_ARRVAL_P(&EG(symbol_table)));
    nxt_php_reset_server_vars(ctx);

    // 2. Reset php://input
    php_stream_rewind(ctx->input_stream);

    // 3. Flush output buffers
    while (ob_get_level() > 0) ob_end_clean();

    // 4. Call user reset hook (registered via freeunit_register_reset())
    if (ctx->reset_callback) {
        ctx->reset_callback();
    }
}
```

The **hard part** is not the C code — it's testing against every major Laravel
package to find state leaks. Octane's experience shows that:
- Most Laravel core services are clean (Octane team already fixed them)
- Problem areas: packages with static caches (some payment SDKs, legacy libs)
- Solution: comprehensive test suite + clear documentation

---

## 7. Timeline & Dependencies

```
X4 Persistent-worker contract (3w)
  │
  ▼
P4 PHP persistent worker mode (4-6w)
  │
  ├──► PHP extension API: freeunit_handle_request() (1w)
  │
  ├──► State reset hooks (1w, parallel with above)
  │
  ▼
freeunit/octane-driver package (2-3w, community)
  │
  ├──► CI: Laravel Octane test matrix (1w)
  │
  ├──► Benchmark: FreeUnit vs FrankenPHP vs RoadRunner (1w)
  │
  ▼
Blog post + Laracon/DrupalCon talk
```

**Critical path to "Octane-ready":** ~10-13 weeks from when X4 starts.

---

## 8. Key Insight

FreeUnit P4 is architecturally closest to **FrankenPHP** (embedded SAPI,
persistent worker), but with three structural advantages:

1. **No Go dependency** — pure C, smaller binary, no Go GC
2. **io_uring** — zero-copy I/O path (once RECV tier lands)
3. **Kernel-arbitrated dispatch (BWP)** — structural advantage under load

The Laravel community already accepts the persistent-worker model (Octane has
~4M downloads). The question is not "will they adopt it" but "which backend
will they choose." FreeUnit's answer: **the fastest one with the fewest
dependencies.**
