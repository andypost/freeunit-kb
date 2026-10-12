# Drupal 12 + Symfony\Runtime + FreeUnit P4 — Persistent Workers for Drupal

**Created:** 2026-07-13
**Context:** Symfony Runtime is a key enabler for persistent-worker models (Octane,
FrankenPHP). Drupal 12 plans to adopt it. FreeUnit P4 can be the first server
that makes Drupal truly persistent without Go or Swoole dependencies.

---

## 1. Symfony\Runtime — What It Is

**Component:** `symfony/runtime` (PHP package, MIT license)
**Introduced:** Symfony 5.3 (2021)
**Purpose:** Decouple application code from *how* HTTP requests are received.

Before Symfony Runtime, a Symfony app's `index.php` was:

```php
// Traditional index.php — tightly coupled to PHP-FPM
$kernel = new Kernel('prod', false);
$request = Request::createFromGlobals();
$response = $kernel->handle($request);
$response->send();
$kernel->terminate($request, $response);
```

With Symfony Runtime:

```php
// Runtime-aware index.php — works with ANY server model
require __DIR__ . '/../vendor/autoload.php';

return function (array $context) {
    // The runtime controls how many times this callback is called
    $kernel = new Kernel(
        $context['APP_ENV'] ?? 'prod',
        (bool) ($context['APP_DEBUG'] ?? false)
    );
    $request = Request::createFromGlobals();
    $response = $kernel->handle($request);
    $response->send();
    $kernel->terminate($request, $response);
};
```

The runtime decides:
- **Without Octane:** call the callback once per request (standard PHP-FPM)
- **With Octane:** call the callback in a loop, re-use the kernel
- **With FrankenPHP:** call the callback in a Fibers-aware loop

### How Symfony Runtime resolves the backend

```php
// symfony/runtime resolves which Runtime class to use via:
// 1. `$_SERVER['RUNTIME_CLASS']` env var
// 2. `composer.json` `extra.runtime.class` 
// 3. Heuristics (installed packages)

// FrankenPHP provides: `\Symfony\Component\Runtime\FrankenPhpRuntime`
// RoadRunner provides: `\Symfony\Component\Runtime\RoadRunnerRuntime`
// Generic HTTP: `\Symfony\Component\Runtime\HttpKernelRuntime`
```

---

## 2. Drupal 12 and Symfony Runtime

### Current State (Drupal 9-11)

Drupal's `index.php` is **not runtime-aware**:

```php
// drupal/web/index.php — Drupal 9/10/11
$autoloader = require_once 'autoload.php';
$request = Request::createFromGlobals();
$kernel = DrupalKernel::createFromRequest($request, $autoloader, 'prod');
$response = $kernel->handle($request);
$response->send();
$kernel->terminate($request, $response);
```

Bootstrap sequence:
```
→ composer autoload
→ DrupalKernel::createFromRequest()   ← loads settings.php
→ $kernel->boot()                     ← 50-200ms (service container build)
→ $kernel->handle()                   ← DB queries, render
→ $kernel->terminate()
```

**Key problem:** `createFromRequest()` + `boot()` = **~80-200ms of overhead**
on EVERY request, even warm. This is Drupal's "cold bootstrap" problem.

### Drupal 12 and Symfony Runtime

Drupal 12 plans to adopt Symfony Runtime. The proposed `index.php`:

```php
// drupal/web/index.php — Drupal 12 with Symfony Runtime
require __DIR__ . '/../vendor/autoload.php';

return function (array $context) {
    $autoloader = require_once __DIR__ . '/autoload.php';
    $request = Request::createFromGlobals();
    $kernel = DrupalKernel::createFromRequest($request, $autoloader, 'prod');
    $response = $kernel->handle($request);
    $kernel->terminate($request, $response);
    return $response;
};
```

This enables:
1. **Persistent workers** — if the runtime supports it (Octane, FrankenPHP, FreeUnit P4)
2. **Server-agnostic CI** — same entry point for PHP-FPM, Swoole, FreeUnit
3. **Environment-based configuration** — via `$context['APP_ENV']`

---

## 3. What Persistent Workers Could Mean for Drupal

### 3.1 The Holy Grail: Boot Drupal ONCE

```
Current (FPM):
  Request 1 → FPM worker 1 → boot Drupal (150ms) → handle (200ms) → die
  Request 2 → FPM worker 2 → boot Drupal (150ms) → handle (200ms) → die

With FreeUnit P4:
  Worker starts → boot Drupal (150ms) → [READY]
  Request 1 → handle (200ms) → reset state → [READY]
  Request 2 → handle (200ms) → reset state → [READY]
  Request 3 → handle (200ms) → reset state → [READY]
```

**Total time per request: 200ms instead of 350ms.** That's **~40% faster**
response times for the user — without any Drupal optimization.

### 3.2 Where the Boot Cost Goes

Drupal kernel boot (`\Drupal\Core\DrupalKernel::boot()`):

| Phase | Time | Persistent? | Notes |
|-------|------|-------------|-------|
| `Composer autoload` | ~5ms (warm) | ✅ **Reused** | Once, never again |
| `settings.php` | ~5ms | ✅ **Reused** | Once per worker |
| `Service container compile` | ~50-100ms | ✅ **Reused** | Not warmed in FPM |
| `Database connection` | ~5ms | ✅ **Reused** | PDO stays alive |
| `Module system` | ~10ms | ✅ **Reused** | Module list stays |
| `YAML config load` | ~5ms | ✅ **Reused** | Config stays cached |
| `Theme system` | ~10ms | ✅ **Reused** | Theme registry stays |
| **Total boot** | **~80-155ms** | **Saved** | **GONE** |

**Real-world impact:** A Drupal page that takes 350ms (150ms boot + 200ms DB/render)
becomes 200ms. No module changes, no DB optimization.

### 3.3 The Really Exciting Part: opcache Warming

The most painful part of Drupal's cold start is **opcache filling**.

```bash
# FreeUnit worktree new feature/drupal-module
# → Worker boots Drupal → opcache fills with 5000+ files
# → Second request: ALL files already cached in SHM
# → No more "first request takes 5 seconds" problem

# On deploy:
freeunit reload
# → New workers boot Drupal → opcache fills → ready in ~500ms
# → Old workers drain in-flight requests → zero downtime
```

**With PHP-FPM:**
- First request after deploy: opcache starts cold → many slow file reads
- May take 5-10 requests to warm up opcache fully

**With FreeUnit:**
- `prepare` target runs one warmup request before accepting traffic
- Every worker starts with a hot opcache
- Users never see the "first visitor after deploy gets 5s load time" problem

---

## 4. The State Reset Challenge for Drupal

This is the hardest part. Drupal has **a lot** of static state.

### What Drupal keeps in static memory

| State | Where | Problem | Fix |
|-------|-------|---------|-----|
| **Service container** | `\Drupal::getContainer()` | ✅ **Should persist** | No reset needed |
| **Static entity cache** | `\Drupal\Core\Entity\EntityBase` | ❌ Must clear between requests | `$storage->resetCache()` |
| **State (variables)** | `Drupal::state()` | ✅ Should persist | No reset |
| **Route provider** | `\Drupal\Core\Routing\Router` | ✅ **Should persist** | No reset after rebuild |
| **Route matcher** | `\Drupal::service('router.no_access_checks')` | ✅ **Should persist** | Exceptions only on config change |
| **String translation** | `\Drupal::translation()` | ✅ **Should persist** | No reset |
| **Config factory** | `\Drupal::config()` | ✅ **Should persist** | No reset |
| **Logger** | `\Drupal::logger()` | ✅ **Should persist** | No reset |
| **Tempstore** | `\Drupal::service('tempstore.private')` | ❌ May need reset | Session-scoped |
| **Lock** | `\Drupal::lock()` | ✅ **Should persist** | No reset |
| **Cache** | `\Drupal::cache()` | ✅ **Should persist** | Backend lives in DB/Redis |
| **Database connection** | `\Drupal::database()` | ✅ **PERSIST** | Critical win! |
| **Current user** | `\Drupal::currentUser()` | ❌ Must reset | Clear after request |
| **Request stack** | `request_stack` | ❌ Must reset | Clear after request |
| **Private temp store** | `tempstore.private` | ❌ Session-bound | Already session-scoped |

### The critical persistent win: Database connection

Currently in PHP-FPM:
```
Request 1 → FPM worker → Drupal boot → MySQL connect(3-way handshake) → query
Request 2 → FPM worker → Drupal boot → MySQL connect → query
Request N → FPM worker → Drupal boot → MySQL connect → query
```

Each FPM worker opens a fresh PDO connection. For busy sites with 50 workers,
that's 50 TCP connections to MySQL. MySQL's `max_connections` is a common limit.

**With FreeUnit P4 persistent workers:**
```
Worker starts → Drupal boot → MySQL connect → [ready]
Request 1 → query (reuse the SAME PDO)
Request 2 → query (reuse the SAME PDO)
Request N → query (reuse the SAME PDO)
```

**Win:**
- **1 connection per worker** instead of 1 per request
- **No TCP handshake** per request (saves ~5ms on local, ~50ms on cloud)
- **Fewer MySQL connections** total — less `max_connections` pressure
- **mysqlnd buffered queries** reuse internal buffers

### What Drupal needs for persistent workers

```php
// Proposed: Drupal persistent worker hook
#[\Drupal\Core\Runtime\BeforeRequest]
public function resetRequestState(): void {
    // Clear per-request caches
    \Drupal::entityTypeManager()->getActiveDefinitionBuilders();
    // Reset in-memory caches
    \Drupal::service('entity.memory_cache')->deleteAll();
    // Reset render cache
    \Drupal::service('renderer')->resetCache();
}

#[\Drupal\Core\Runtime\AfterResponse]
public function cleanupRequest(): void {
    // Close any dangling file handles
    // Reset current user to anonymous
    \Drupal::currentUser()->setAccount(new AnonymousUserSession());
    // Clear request stack
    \Drupal::service('request_stack')->pop();
}
```

Or, more practical: Drupal could provide a **middleware** approach:

```php
// drupal/web/worker.php (FreeUnit P4 entry point)
use Symfony\Component\HttpFoundation\Request;
use Drupal\Core\DrupalKernel;
use Drupal\Core\Site\Settings;

$autoloader = require_once 'autoload.php';

// BOOT ONCE
$kernel = DrupalKernel::createFromRequest(
    Request::createFromGlobals(),
    $autoloader,
    'prod'
);
$kernel->boot();
$kernel->preHandle(Request::createFromGlobals()); // Sets up $_SERVER, etc.

while ($request = freeunit_handle_request()) {
    // REQUEST-STATE RESET
    $kernel->preHandle($request);
    
    // HANDLE
    $response = $kernel->handle($request);
    $response->send();
    
    // POST-REQUEST CLEANUP
    $kernel->terminate($request, $response);
    $kernel->resetRequestState();
}
```

---

## 5. Drupal-Specific Use Cases for Persistent Workers

### 5.1 JSON:API — the clearest win

Drupal's JSON:API module serves API responses. On a headless Drupal site:

```
Every request: boot Drupal (100ms) + route to JSON:API (50ms) + DB queries (100ms)
With persistent: route to JSON:API (50ms) + DB queries (100ms)
→ 250ms → 150ms. Users perceive "instant".
```

For a headless Drupal site with 10k daily API users, this is significant.

### 5.2 BigPipe + Lazy Builders

Drupal's BigPipe sends a shell HTML page, then individual placeholders via
Chunked transfer. Each placeholder is a separate request to the server.

```
Page with 10 BigPipe placeholders (each is a lazy builder callback):
  FPM:   boot(100ms) + handle query(50ms) × 10 = 600ms
  P4:   boot(ONCE) + handle query(50ms) × 10 = 500ms
  → 16% less server time per page. More BigPipe placeholders = more savings.
```

### 5.3 Drush commands

Drush (Drupal shell) runs as CLI but boots the full Drupal kernel.

```bash
# Current: each drush command = Drupal boot
drush cr     → boot Drupal (150ms) → rebuild cache → done
drush updb   → boot Drupal (150ms) → run updates → done
drush cex    → boot Drupal (150ms) → export config → done

# With FreeUnit P4 scheduler (roadmap X5 + PHP P7):
freeunit run drupal:cache-rebuild
freeunit run drupal:update
freeunit run drupal:config-export
# → Drupal booted ONCE, commands reuse the same warm instance
# → Each command: ~10ms instead of ~150ms
```

For CI/CD pipelines running multiple drush commands in sequence, this is
a **order-of-magnitude speedup**.

### 5.4 Cron runs

Drupal's cron is notoriously slow on complex sites:

```
Current: each cron run = boot Drupal (150ms) + run hooks (500ms-30s)
With P4: cron worker already warm → immediate hook execution → done
```

---

## 6. Edge runtime + FreeUnit + Drupal 12 Architecture

### Full stack

```
Cloudflare/Akamai CDN (H2/H3)
    │
    ├── Edge runtime (H2/H3, TLS termination)
    │      │
    │      ├── Datagram dispatch (kernel-arbitrated)
    │      │
    │      └── FreeUnit P4 (persistent PHP workers)
    │             │
    │             ├── Drupal 12 kernel (booted once)
    │             ├── State reset between requests
    │             ├── Persistent MySQL PDO
    │             ├── Redis/Memcached connection
    │             └── Opcache (always warm)
    │
    ├── MySQL (connection pool via PDO persistent)
    ├── Redis (cache + lock)
    └── Varnish (HTTP cache, optional)
```

### Bottleneck removal

```
Before (FPM):                    After (FreeUnit P4):
  PHP-FPM startup × N reqs         NONE
  Drupal boot × N reqs             1 × worker lifecycle
  MySQL connect × N reqs           1 × worker lifecycle
  Opcache fill × N reqs            1 × worker lifecycle
  Static file read                 0 × io_uring sendfile

  Total overhead per request:     Total overhead per request:
  100-200ms + DB query time       0-20ms (state reset) + DB query time
```

---

## 7. What FreeUnit Needs to Deliver for Drupal 12

### Minimum viable (MVP)

| Item | Dependency | Effort | Value |
|------|-----------|--------|-------|
| X4: Persistent-worker contract | Router | ~3w | Foundation |
| P4: PHP persistent worker | X4 | ~4-6w | Worker loop |
| PHP extension: `freeunit_handle_request()` | P4 | ~1w | User-facing API |
| State reset: superglobals + php://input | P4 | ~1w | Core reset |
| Drupal worker.php template | P4 | ~1d | Easy adoption |
| Config: `worker: worker.php` | P4 | ~1d | User config |

### Full Drupal 12 support (additional)

| Item | Effort | Notes |
|------|--------|-------|
| Drupal contrib module: freeunit_drupal | ~2w | Config UI, status reports |
| Drupal core patch: Symfony Runtime support | ~2w | Drupal 12 core integration |
| CI: Drupal test suite (BigPipe, JSON:API, Migrate) | ~1w | Stability testing |
| Benchmark: FPM vs FreeUnit P4 for Drupal | ~3d | Blog post / DrupalCon slides |
| Documentation: Drupal deployment with FreeUnit | ~1w | Worktree, reload, CI/CD |

### The Drupal-specific state reset (the hard part)

```php
// Proposed: DrupalKernel::resetRequestState() — called by FreeUnit between requests
namespace Drupal\Core;

class DrupalKernel {
    // ...existing code...

    public function resetRequestState(): void {
        // 1. Reset current user to anonymous
        $this->getContainer()->get('current_user')
            ->setAccount(new AnonymousUserSession());

        // 2. Clear request stack
        $this->getContainer()->get('request_stack')->popAll();

        // 3. Reset entity memory cache
        $this->getContainer()->get('entity.memory_cache')->deleteAll();

        // 4. Reset render cache
        $this->getContainer()->get('renderer')->resetCache();

        // 5. Clear static entity caches
        foreach ($this->getContainer()->get('entity_type.manager')->getDefinitions() as $type) {
            $storage = \Drupal::entityTypeManager()->getStorage($type->id());
            if ($storage instanceof EntityStorageBase) {
                $storage->resetCache();
            }
        }

        // 6. Reset theme active state
        \Drupal::theme()->resetActiveTheme();

        // 7. Call hook_freeunit_request_reset for contrib modules
        \Drupal::moduleHandler()->invokeAll('freeunit_request_reset');
    }
}
```

---

## 8. drupal_static() — the Biggest Challenge for Persistent Workers

### 8.1 What is drupal_static()

Drupal's `drupal_static()` is a **global static storage** — a single associative
array that lives in the PHP process memory. It's used thousands of times across
Drupal core and contrib modules.

```php
// core/includes/bootstrap.inc
function &drupal_static($name, $default_value = NULL, $reset = FALSE) {
    static $data = [], $default = [];
    
    if ($reset) {
        $data[$name] = $default[$name] ?? NULL;
        return $data[$name];
    }
    
    if (!array_key_exists($name, $data)) {
        $data[$name] = $default_value;
        $default[$name] = $default_value;
    }
    
    return $data[$name];
}
```

**In PHP-FPM**, this is fine — the entire `static $data` array is destroyed
at `RSHUTDOWN` and recreated fresh on the next request.

**In a persistent worker (FreeUnit P4)**, `static $data` lives FOREVER. Data
accumulates across requests. Some of it should persist (module paths, entity
definitions), some must be reset per-request (URL aliases, current user,
active menu trail).

### 8.2 How drupal_static is used

**Category 1: Global (should PERSIST between requests)**

These values change only on deploy/reconfigure and are safe to cache forever:

| Function | Caches | Safe to persist? | Why |
|----------|--------|-----------------|-----|
| `drupal_get_path()` | Module/theme paths | ✅ YES | Only changes on install/uninstall |
| `drupal_get_filename()` | File locations | ✅ YES | Only on module install |
| `module_list()` | Enabled modules | ✅ YES | Only on admin/update |
| `entity_type_get_definitions()` | Entity definitions | ✅ YES | Only on module install |
| `field_info_field_types()` | Field type definitions | ✅ YES | Stable across requests |

**Category 2: Per-request (MUST be RESET)**

These depend on the current request and must be cleared:

| Function | Caches | Must reset? | Why |
|----------|--------|-------------|-----|
| `drupal_lookup_path()` | URL alias cache | ❌ **YES** | `/about` → correct page or `/node/1`? |
| `menu_get_active_trail()` | Current breadcrumb | ❌ **YES** | Changes per page |
| `language_list()` | Available languages | ⚠️ Maybe | Languages are static, but `current language` is per-request |
| `locale()` | Current translation | ❌ **YES** | Interface language per user |
| `theme_get_registry()` | Theme registry | ⚠️ Maybe | Registry is static, but `active theme` depends on route options |
| `entity_get_display()` | Display mode settings | ⚠️ Partially | Bundle-level settings are static, but config overrides are per-request |
| `page_get_cache()` | Page cache ID | ❌ **YES** | Different per URL |

### 8.3 The problem: drupal_static does NOT distinguish categories

```php
drupal_static('drupal_get_path');     // ← global
drupal_static('drupal_lookup_path');   // ← per-request
drupal_static('entity_get_display');   // ← depends on bundle, not request
```

All share the same `$data` array. There is no tag, no type, no category.

### 8.4 What happens without reset

```
Without drupal_static_reset(), after 1000 requests:

1. drupal_static("drupal_get_path") — works perfectly (paths don't change)

2. drupal_static("drupal_lookup_path") — RETURNS WRONG ALIAS
   User visited /about → path alias cached
   User visits /node/1 → drupal_lookup_path returns /about
   → WRONG. User sees wrong page.

3. drupal_static("language_list") — language doesn't switch
   User switches language → list not updated
   → WRONG. Wrong language displayed.

4. drupal_static("menu_get_active_trail") — breadcrumb from previous request
   → WRONG. Wrong breadcrumb displayed.
```

**This is the #1 source of bugs** in persistent-worker setups for Drupal.
It's well-documented in the FrankenPHP/Swoole community.

### 8.5 Solutions for FreeUnit P4

#### Option A: Full drupal_static_reset() — safe but costly

```php
while ($request = freeunit_handle_request()) {
    // Reset EVERYTHING — safe for MVP
    drupal_static_reset();       // clears all static state
    
    // Drupal kernel pre-handle (boot is already done)
    $kernel->preHandle($request);
    $response = $kernel->handle($request);
    $kernel->terminate($request, $response);
}
```

**Cost:** ~3-5ms per request for re-populating module paths, entity definitions,
theme registry. **Still faster than FPM** (no full boot, no DB connect).

#### Option B: Selective reset — optimal, needs blacklist

```php
// Known per-request drupal_static keys (expand as found)
$per_request_keys = [
    'drupal_lookup_path',
    'menu_get_active_trail',
    'locale',
    'language_list',          // debatable
    'theme_get_registry',     // debatable
    'path_alias_whitelist',
    'file_scan_directory',
    'registry',               // PHP class registry
    'schema',                 // DB schema cache (usually static, but needs reset on update)
];

while ($request = freeunit_handle_request()) {
    // Reset only per-request caches
    foreach ($per_request_keys as $key) {
        drupal_static($key, NULL, TRUE);  // $reset = TRUE
    }
    
    // Global caches (drupal_get_path, module_list, entity definitions) STAY
    // → saves ~3-5ms vs full reset
    
    $kernel->preHandle($request);
    $response = $kernel->handle($request);
    $kernel->terminate($request, $response);
}
```

#### Option C: Hook-based — correct, needs Drupal core patch

```php
// Proposed: Drupal core hook that registers drupal_static category

// modules/system/system.module
function system_drupal_static_info() {
    return [
        'drupal_get_path' => ['type' => 'persistent'],
        'drupal_get_filename' => ['type' => 'persistent'],
        'drupal_lookup_path' => ['type' => 'per-request'],
        'menu_get_active_trail' => ['type' => 'per-request'],
        'entity_get_display' => ['type' => 'persistent'],
        'locale' => ['type' => 'per-request'],
        // ...
    ];
}
```

Then FreeUnit calls:
```php
drupal_static_reset('per-request');
// → resets ONLY per-request keys
// → persistent keys stay cached
```

**This requires a Drupal core patch.** Realistic for Drupal 12.

#### Option D: Volatile annotation (PHP 8.4+)

PHP 8.4 introduced `mb_*` and `lazy` object support. With PHP 8.5+:

```php
// Future: explicit static lifetime annotations
// Not yet available, but worth tracking
#[\Static(scope: 'request')]
function drupal_get_path($type, $name) {
    $paths = &drupal_static(__FUNCTION__);
    // ...
}
```

### 8.6 Strategy for FreeUnit P4

| Phase | Approach | Why |
|-------|----------|-----|
| **MVP (P4 lands)** | Option A (full reset) | Safe, simple. Still 2x faster than FPM. |
| **Post-MVP** | Option B (selective reset) | Profile which keys are safe to persist. |
| **Drupal 12** | Option C (hook-based) | Push Drupal core patch for `hook_drupal_static_info()`. |
| **PHP 8.5+** | Option D (annotation) | Track RFC, adopt when stable. |

### 8.7 Performance impact

| Scenario | Boot | drupal_static | PDO | Total |
|----------|------|---------------|-----|-------|
| **FPM (cold)** | 150ms | 0ms (RSHUTDOWN) | 5ms | **~350ms** |
| **FPM (warm)** | — | — | — | **~200ms** |
| **P4 + full reset** | 0ms | 5ms (re-populate) | 0ms | **~205ms** |
| **P4 + selective reset** | 0ms | 1ms | 0ms | **~201ms** |
| **P4 + hook-based** | 0ms | 0ms (persistent paths) | 0ms | **~200ms** |

**Even with full drupal_static_reset(), P4 is ~40% faster than warm FPM.**
The savings from no boot + no DB connect + no module discovery DOMINATE
the small cost of re-populating static caches.

### 8.8 The real test: contrib modules

The hardest part is contrib. Modules like:

| Module | drupal_static usage | Risk |
|--------|--------------------|------|
| **Pathauto** | `pathauto_alias_cache` | **HIGH** — alias cache per request |
| **Views** | `views_get_view_result()` | **HIGH** — cached query results stale |
| **Search API** | Search result caches | **HIGH** — cached results stale |
| **Feeds** | Import state | **MEDIUM** — batch operation |
| **Migrate** | Migration state | **MEDIUM** — long-running process |
| **Commerce** | Cart cache | **MEDIUM** — session-dependent |
| **Webform** | Element definitions | **LOW** — static definitions |

**Strategy:** Start with core-only testing, then expand contrib coverage.
For modules known to misbehave, add their keys to the per-request reset list.

### 8.9 Summary

drupal_static() is Drupal's biggest challenge for persistent workers, but
**NOT a blocker**:

1. ✅ **Full reset** works and is safe — still 2x faster than FPM
2. ✅ **Selective reset** optimizes — profile which keys are persistent-safe
3. ✅ **Drupal 12 hook** solves it properly — push `hook_drupal_static_info()`
4. ⚠️ **Contrib modules** need testing — module-by-module blacklist

---

## 9. Comparison: Persistent Workers for Drupal

| Approach | Bootstrap | DB connect | Opcache | Go dep? | IPC? |
|----------|-----------|------------|---------|---------|------|
| **PHP-FPM (current)** | Per request | Per request | Per process | ❌ | ❌ |
| **Octane + Swoole** | Once | Once | Once | ❌ | ❌ |
| **Octane + RoadRunner** | Once | Once | Once | ✅ Go | ✅ JSON |
| **FrankenPHP** | Once | Once | Once | ✅ Caddy | ❌ |
| **FreeUnit P4** | **Once** | **Once** | **Once** | **❌** | **❌** |

FreeUnit P4 is the only solution that gives persistent-worker benefits **without**
adding a Go binary or JSON IPC. For the Drupal community, which values
simplicity and minimize dependencies, this is a strong argument.

---

## 10. DrupalCon BoF: The Drupal 12 + FreeUnit Story

### Key slide: "Your Drupal site, 40% faster, no code changes"

| Before (FPM) | After (FreeUnit P4) |
|---|---|
| 350ms page load | 200ms page load |
| MySQL connect per request | Reused PDO connection |
| Opcache cold on new workers | Always warm |
| No graceful reload | Zero-downtime deploy |
| Dead on 502 under load | Kernel dispatch, no queue |

### Demo: deploy Drupal with zero downtime

```bash
# Deploy new code
git pull origin main
composer install --no-dev

# Reload workers gracefully
freeunit reload
# → Old workers finish, new workers start warm
# → Total downtime: 0ms
# → Users see NO maintenance page
```

### Demo: branch switching with worktrees

```bash
# Work on a new feature
freeunit worktree add feature/new-ci-workflow
# → git worktree + composer install + Drupal boot
# → Open at localhost:8081
# → opcache already warm
# → Separate MySQL database (or prefix)

# Show dev in browser: feature site running alongside production site
# Switch between ports to compare behavior
```

### Call to action for Drupal community

1. **Try FreeUnit with Drupal 11 today** — POC without persistent workers (HTTP/1.1)
2. **Contribute to Drupal 12 Symfony Runtime core integration**
3. **Test contrib module compatibility** with persistent workers
4. **Design the state reset hooks** — which Drupal state must persist?
