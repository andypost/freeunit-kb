# opcache in FreeUnit — in-process vs fork, and what it means for stubs

**Date:** 2026-09-11 · **Status:** verified live on running unitd 1.36.1 (PHP 8.4.25)
**Context:** answer to "can jobs be in-process or forked to share opcache?"

## The three different questions (they have different answers)

| Question | Answer | Why |
|----------|--------|-----|
| Do Unit's **PHP web workers** share opcache? | ✅ **YES** (proven) | workers are **forked from a prototype process** → same opcache SHM |
| Can a **stub's job run in-process** (inside the Unit PHP worker)? | ❌ in this build | PHP SAPI has **no boot hook** (TrueAsync not compiled) — no code point to start a loop |
| Does a stub's **child `php artisan`** inherit the worker's opcache? | ❌ no | it's a **fresh CLI process** spawned via exec, not forked from the worker |

## Proof: opcache IS shared across forked workers

Setup: PHP app (`type: php`) with 2 workers (`spare:2, max:2`), opcache on.
Test: warm a script (`opcache_compile_file`), then `opcache_reset()` **from one
worker**, then re-check **both**.

```
warm   -> both pids report sees_warmtarget=YES
reset  -> pid=10575 RESET=ok            (one worker)
check  -> pid=10574 sees=no ; pid=10575 sees=no   <-- BOTH cleared
```
A reset in worker A cleared worker B's cache → **shared SHM segment** → Unit's
prototype+fork model makes all workers share one opcache. (`mem_used` was also
byte-identical across pids: 9168664.)

This is `nxt_router_prefork` / prototype workers (`nxt_router.c`): the prototype
boots the interpreter **once**, forks workers that inherit the warm opcache.

## How to actually enable opcache in a Unit PHP app

`zend_extension` is a **startup-only** PHP directive — it CANNOT be set via the
app's `options.admin`/`options.user` (those apply at runtime). Two facts:

- `opcache.so` ships as a **separate package** (`php84-opcache`), loaded by
  `zend_extension=opcache` in php.ini.
- Unit reads php.ini from `options.file` — point it at a php.ini containing:
  ```ini
  zend_extension=/usr/lib/php84/modules/opcache.so   ; absolute path required
  opcache.enable=1
  opcache.enable_cli=1
  opcache.memory_consumption=128
  opcache.validate_timestamps=0        ; prod: never re-stat
  opcache.max_accelerated_files=5000
  ```
Verified: with `options.file` → `opcache_enabled=yes`, `cached_scripts=1`.

## What this means for the worker stubs (artisan / drupal / wp)

Our stubs run the job as a **child CLI process** (`php artisan queue:work …`,
`drush …`, `wp …`) spawned by the Python supervisor. That child is a **separate
LSAPI/CLI PHP process** → it does **NOT** see the Unit worker's opcache.

Two ways to still get opcache benefit for CLI jobs:

1. **`opcache.file_cache`** (the CLI answer). A **second-level, file-based**
   cache that survives across processes:
   ```ini
   opcache.enable_cli=1
   opcache.file_cache=/var/cache/php-opcache
   opcache.file_cache_only=1        ; in-memory SHM unused for pure-CLI
   ```
   The CLI job then reuses compiled opcodes from disk across runs. Caveat:
   `opcache_reset()`/`opcache_invalidate()` are no-ops in `file_cache_only` mode.
2. **Run the job IN-process** — would inherit the worker's SHM opcache for free,
   but blocked: PHP has no boot hook here (same reason a PHP stub can't self-start).
   Unblocked only by rebuilding the module with `NXT_PHP_TRUEASYNC` (entrypoint).

## Bottom line

- **fork**: ✅ real and already working — Unit forks web workers from a prototype,
  and they share one opcache SHM segment. This is the big opcache win for **WP/Drupal
  web traffic**, and needs **no code** — just `options.file` with opcache enabled.
- **in-process**: ❌ not available in this build for PHP jobs (no boot hook) — the
  same TrueAsync gap that blocks a pure-PHP stub.
- **stub child processes**: separate opcache → use **`opcache.file_cache`** for
  CLI-level reuse; the shared-SHM win does not extend to exec'd children.

## Related

- `freeunit-1361-rootless-live-test.md` — PHP module RUNPATH/TrueAsync facts.
- `artisan-worker-stubs.md` / `drupal-cron-queue-stub.md` / `wordpress-cron-queue-stub.md`
  — the stub supervisors whose children this concerns.
- Roadmap: **P4 persistent workers** + **prototype+fork (shared opcache)** — P4 is
  what would let the *job itself* run in-process and inherit the warm opcache.
