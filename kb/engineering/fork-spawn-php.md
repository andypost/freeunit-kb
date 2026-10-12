# Fork-spawn for Unit PHP — long jobs without TrueAsync

**Date:** 2026-09-11 · **Status:** built + tested live on running unitd 1.36.1 (PHP 8.4.25)
**Artifact:** `tools/artisan_stubs/fork_spawn.php`

## The idea (all verified)

A Unit PHP worker is **long-lived** and its opcache is **warm** (it was forked
from the prototype). So inside a plain request handler we `pcntl_fork()`:

| Effect | Why |
|--------|-----|
| **CHILD inherits opcache SHM** | fork shares memory; child sees the parent's compiled scripts |
| **PARENT returns HTTP at once** | the request never waits on the job → **no request-timeout breach** |
| **worker detaches** | `setsid` + a **double-fork** → orphan reparented to init, **no zombie** |

→ Long-running / scheduled work (Drupal cron, `queue:run`, WP cron, artisan) with
**no TrueAsync** — the trigger is a normal HTTP request the existing stub ticker
already makes. This is the "спан", and it closes the "PHP has no boot hook" gap
without rebuilding the module.

## Proofs (live)

1. **Fork inherits opcache** — parent warms a script, forks; child reports
   `opcache=on sees_warm=YES`. ✔
2. **Return is instant, job continues** — `?job=sleep&secs=6`:
   response in **6 ms**, child logged `start … exit took=6.000s` after the request
   was already done. ✔ (Breaches any request timeout by design — the job is not
   tied to the request.)
3. **No zombie** — after double-fork + `setsid`, the worker completed and
   `ps … stat ~ Z` was **empty**. ✔

## Why this is optimal for Drupal (and good for tests / blue-green)

- **Drupal cron/queue are one-shot** → a fork-spawn per tick is the natural fit;
  the child runs the Drupal bootstrap **in-process** (warm opcache → cheap) rather
  than exec'ing a cold `drush`.
- **Tests**: trigger jobs by `curl` and read the result — no CLI, no host cron.
- **Blue/green**: the spawn returns immediately, so a deploy can fire warm-up /
  drain jobs in the background while the request path stays responsive; old and
  new workers coexist (fork inherits whichever config was live).

## Timeouts — the important caveat

The parent must **not** wait on the child. Use `pcntl_waitpid($pid, …, WNOHANG)`
(or the double-fork, as here). Then:
- request timeout is **irrelevant** to the job (job outlives the request);
- but **nothing supervises the orphan** — if it dies mid-run, that run is lost.
  For at-least-once semantics, pair with a lock/dedup (Drupal's own queue lease,
  or a lockfile) so the next tick re-claims.

## Relation to TrueAsync / P4

- **TrueAsync** (`NXT_PHP_TRUEASYNC` + `entrypoint`) = a *clean* boot hook, but
  our module isn't built with it. The fork-spawn reaches the same goal **today**.
- **P4 (persistent workers)** is still the bigger prize: a job running **in the
  worker's own context** with zero fork overhead. Fork-spawn is the pragmatic
  stepping stone: same warm-opcache benefit, no core change.

## Wiring

```json
"applications": {
  "spawner": {
    "type": "php", "root": "/var/www/html", "script": "fork_spawn.php",
    "processes": { "spare": 1, "idle_timeout": 0 },
    "options": { "file": "/etc/php/opcache-pcntl.ini" }
  }
}
```
php.ini needs: `zend_extension=opcache.so`, `extension=pcntl.so`,
`extension=posix.so`, `opcache.enable=1`, `opcache.validate_timestamps=0`.

Trigger: `curl 'http://app/fork_spawn.php?job=cron'` (or `?job=queue&name=foo`),
or from the existing Python stub ticker — one request per tick.

## Open items

- ~~Real Drupal bootstrap in the child (`DrupalKernel` + `\Drupal::service('cron')`)~~
  **done + measured** — `fork-spawn-drupal-measurement.md`: warm tick 0.049 s vs 0.42 s cold CLI.
- ~~drupal_stub.py ticker switched from spawning `drush` to the endpoint~~ **done** —
  `TRIGGER=http` in `drupal_stub.py`; tick 0.004 s vs 0.52 s cold spawn.
- Child logging → structured (currently a file). Note: a Unit **Python** app's stdout is NOT
  forwarded to the Unit log either — the stub mirrors its tick log to `$STUB_LOG`.

## Gotcha: `exit()` does not kill a fork child (found by measuring)

Inside a Unit PHP worker, `exit()` in a fork child hands control **back to Unit's event loop**
instead of terminating: the process keeps `poll()`ing and lingers as an extra "application"
worker — **+2 processes per tick**, forever (and they even accept requests). Fix, verified:

- children terminate with `posix_kill(getmypid(), SIGKILL)` (`zap()`), never `exit()`;
- the request process reaps: `reap()` (`pcntl_waitpid(-1, …, WNOHANG)` drain) **before**
  forking, and again after a 2 ms `usleep` — the killed intermediate would otherwise stay a
  zombie held by the long-lived worker.

After the fix: process count flat, 0 zombies across 13 ticks (cost: ~2 ms of trigger latency).
