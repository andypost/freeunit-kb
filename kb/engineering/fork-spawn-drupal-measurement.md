# fork-spawn × Drupal: measured (kernel+cron, and the stub tick)

**Date:** 2026-09-12 · **Status:** measured live on a rootless unitd 1.36.1 + PHP 8.4.25
**Artifacts:** `tools/artisan_stubs/fork_spawn.php`, `tools/artisan_stubs/drupal_boot_cron.php`,
`tools/artisan_stubs/drupal_stub.py` · **Stand:** `tools/setup-fu-stand.sh` / `start-fu-stand.sh`

Two questions, both answered with real numbers:

1. does a **real** Drupal bootstrap (`DrupalKernel` + `\Drupal::service('cron')->run()`)
   run in the fork child, and how much does the **warm opcache** buy?
2. what does switching the Drupal stub tick from a **cold `drush` spawn** to the
   **fork-spawn endpoint** change **per tick**?

## Setup

- Unit 1.36.1 (rootless, `--otel` build), PHP 8.4.25 + opcache, `options.file` php.ini
  (`opcache.enable=1`, `enable_cli=1`, `validate_timestamps=0`).
- Drupal 11.4.6 on SQLite, site FUTest.
- PHP app `spawnapp` (`fork_spawn.php`, `spare:1 max:1 idle_timeout:0`) on 127.0.0.1:8816,
  `?job=cron|queue|sleep`.
- Trigger: `curl 'http://127.0.0.1:8816/?job=cron'` — the HTTP request returns at once,
  the job runs in a detached fork child.

## Measurement 1 — real kernel + cron in the fork child

`drupal_boot_cron.php` = `autoload.php` → `DrupalKernel::createFromRequest(...,'prod')`
→ `boot()` → `preHandle()` → `\Drupal::service('cron')->run()`, returning `cron_ok`.

**Cold = fresh CLI process** (what `drush core:cron` costs structurally), cached_scripts=592, hits=0:

| run | autoload_s | kernel_s | cron_s | total_s |
|---|---|---|---|---|
| A | 0.0197 | 0.2195 | 0.9062 | 1.1454 |
| B | 0.0218 | 0.1117 | 0.3106 | 0.4441 |
| C | 0.0161 | 0.1052 | 0.2727 | 0.3940 |

**Warm = fork child of the Unit worker** (same SHM, ticks 3 s apart):

| tick | autoload_s | kernel_s | cron_s | total_s | cached | hits | trigger HTTP |
|---|---|---|---|---|---|---|---|
| 1 (fills opcache) | 0.0164 | 0.1046 | 0.2922 | 0.4132 | 593 | 1 | 3.4 ms |
| 2 | 0.0002 | 0.0125 | 0.0397 | 0.0524 | 593 | 594 | 10.5 ms |
| 3 | 0.0002 | 0.0094 | 0.0372 | 0.0468 | 593 | 1187 | 3.7 ms |
| 4 | 0.0003 | 0.0121 | 0.0373 | 0.0496 | 593 | 1780 | 3.9 ms |

**Effect of the warm opcache:** total ≈0.42 s → **≈0.049 s** (≈8.5×), kernel 0.11 → 0.011
(≈10×), cron 0.29 → 0.038 (≈7.5×). `cron_ok=true`, `cron_result=true`.

Two facts behind those two numbers:

- `cached_scripts` freezes at **593** across ticks while `hits` grows monotonically
  (1 → 594 → 1187 → 1780): every child compiles **nothing** new and everything it runs is
  a hit — the opcache SHM is genuinely shared between the worker, its forks and siblings.
- **Tick 1 is not cheaper than cold** (0.41–0.48 s): the first child still pays the compile
  of ~592 files into the SHM. The win starts at tick 2 and is permanent thereafter
  (idle_timeout:0 keeps that SHM alive as long as one worker lives).

## Measurement 2 — stub tick: cold `drush` vs fork-spawn endpoint

`drupal_stub.py` got a `TRIGGER` switch (`drush` default | `http`), each tick logging its own
latency; `CRON_INTERVAL=3` so ticks are frequent enough to sample.

| tick | `TRIGGER=http` (fork-spawn) | `TRIGGER=drush` (cold CLI per tick) |
|---|---|---|
| 1 | 0.0185 s | 0.9688 s |
| 2 | 0.0043 s | 0.5214 s |
| 3 | 0.0040 s | 0.5177 s |
| 4 | 0.0042 s | 0.5360 s |
| 5 | 0.0040 s | — |

**Effect per tick: 0.52 s → 0.004 s (≈130×)**, and qualitatively different: the drush-mode tick
**blocks** for PHP start + cold opcache fill + kernel + cron (a real `drush` adds its own
bootstrap on top, so the shim is a lower bound), while the HTTP tick returns in ~4 ms and the
job continues in the background child. A 3 s interval with a 0.52 s tick is 17 % of every
period spent blocked; at 4 ms it is 0.13 %.

## Measurement 3 — the stub tick with **real Drush 13.8.0**

Drush is no longer shipped as a phar: it is a Composer package **installed inside the site**
(`composer require --dev drush/drush`; Composer itself needs `ext-phar`, which Alpine splits
out of `php84` — extract `phar.so` from `php84-phar-*.apk` next to the other module `.so`
files). Drush 13 refuses a global install ("must be installed inside a Drupal site"), and
against a tree that only *looks* like a project its preflight aborts with
`Package "drupal/core" is not installed`.

| what | wall clock |
|---|---|
| `drush core:cron`, standalone (3 runs) | 1.05 / 0.95 / 0.93 s |
| stub tick, `TRIGGER=drush` real Drush (5 ticks) | 1.18 / 0.69 / 0.72 / 0.71 / 0.66 s |
| stub tick, `TRIGGER=http` fork-spawn (5 ticks, same session) | 0.0040 / 0.0046 / 0.0043 / 0.0043 / 0.0041 s |

Same stand, same session ⇒ **≈0.70 s vs ≈0.004 s ≈ 175×** per tick. The earlier 0.52 s
cold-CLI shim was a genuine **lower bound**: real Drush adds ≈0.45 s of its own bootstrap
(container + console + preflight) on top of the PHP start.

## Measurement 4 — queue drain (`queue:run`) cold vs warm

A real queue with a known per-item cost: harness module `fu_queue_test` (one `#[QueueWorker]`,
1 ms sleep + a small CPU loop per item — so the work is separable from the tick's own cost),
50 items per drain, refilled before every run.

| mode | wall clock | items |
|---|---|---|
| cold CLI (`drupal_boot_queue.php`) | 0.31 / 0.26 / 0.27 s | 50 |
| real `drush queue:run fu_queue_test` | 0.69 / 0.68 / 0.67 s (Drush itself reports 0.18–0.19 s of queueing) | 50 |
| warm fork, HTTP trigger `?job=queue&name=…&limit=50` | 0.0055 / 0.0045 / 0.0072 / 0.0034 s (trigger only) | 50 |

Child-side timing of the warm ticks: `kernel_s` 0.006–0.007, `queue_s` 0.170–0.196,
`total_s` 0.177–0.203, `cached_scripts` 623, `hits` 2048 → 4562, `queue_ok=true`.

Reading: the tick's **own** cost (bootstrap) collapses and the trigger returns in ms, while
the **work itself barely moves** — 50 items cost ≈0.18 s in every warm child (≈3.6 ms/item:
the harness's 1 ms plus SQLite claim/delete round-trips). Warm opcache cannot make queue I/O
cheaper; it only removes the per-tick start-up that used to be paid *on top* of it
(0.26 s cold CLI, 0.68 s Drush).

## Memory footprint of a tick

`smaps_rollup` taken while a child was alive (`?job=sleep&secs=8`), plus `/usr/bin/time %M`
for the one-shot processes:

| process | RSS | PSS | private anon | shared |
|---|---|---|---|---|
| Unit worker (parent, warm) | 16.1 MB | 6.0 MB | 2.4 MB | 1.7 MB shmem |
| fork child, alive | 11.0 MB | 3.4 MB | 2.4 MB | 0.2 MB shmem |
| cold CLI process (drain 50) | 36.0 MB peak | — | — | — |
| real Drush process (`queue:run`) | 56.6 MB peak | — | — | — |

A warm child adds ≈11 MB RSS on top of the parent's already-resident opcache pages (≈3.4 MB
PSS, mostly shared): it does **not** re-pay the 36/57 MB a cold CLI / Drush process costs, and
N children share one opcache SHM.

## Bug found while measuring: `exit()` does not kill a fork child

With `exit(0)` in the children, **each tick leaked 2 processes** (the intermediate *and* the
worker): inside a Unit PHP worker, `exit()` returns control to Unit's event loop instead of
terminating, so the child keeps `poll()`ing and lives on as an extra "application" worker —
it even accepts further requests (observed: process count 32 → 48 in 16 s; a leaked child
served the health request of the next session).

Fix, verified (`fork_spawn.php`):

- children die by `posix_kill(getmypid(), SIGKILL)` (`zap()`), never `exit()`;
- the request process reaps what it killed: `reap()` (`pcntl_waitpid(-1, …, WNOHANG)` drain)
  **before** forking (clears the previous tick) and again after `usleep(2000)` (the SIGKILLed
  intermediate would otherwise stay a zombie held by the long-lived worker).

After the fix: process count flat, **0 zombies** across 13 consecutive ticks; the ~2 ms reap
sleep is inside the measured 3.4–4 ms trigger latency.

## Restart hygiene (cost 2 wasted runs)

`pkill`-ing only the unitd **main** leaves controller/router/prototype/workers orphaned to
init; they keep the listening socket and the next unitd dies with
`bind(127.0.0.1:8816) failed (98: Address in use)` — the config then never applies and all
requests go to the stale tree. `start-fu-stand.sh` now kills every `unit:` process and waits
until the port is bindable before exec'ing unitd.

Also: `opcache.validate_timestamps=0` means **editing a stub needs a unitd restart** — a
running worker will keep serving the old compiled script.

## Reproduce

- `bash tools/setup-fu-stand.sh /tmp/fu-pkgs` (rebuild after /tmp is wiped; patchelf RUNPATH)
- `bash tools/start-fu-stand.sh /tmp/fu-pkgs` (port 8816)
- cold baseline: `php84 -c php.ini apps/drupal_boot_cron.php` (prints timing JSON on stderr)
- warm: 4× `curl 'http://127.0.0.1:8816/?job=cron'`, read `cron_boot.out` / `spawn.out`
- stub: python app `drupal_stub` with `TRIGGER=http|drush`, `CRON_INTERVAL=3`, `STUB_LOG=…`

## Caveats

- Single-site stand (SQLite, no realistic content volume): the kernel/cron split is
  representative, absolute cron time is not.
- The trigger returns **before** the job finishes → the job outlives the request and nothing
  supervises it; at-least-once needs a lock/dedup (Drupal's own queue lease or a lockfile).
- `\Drupal::service('cron')->run()` re-enters the site's own state; concurrent ticks (two
  triggers inside the same cron-window) are not deduplicated here.

## Related

- `fork-spawn-php.md` — the pattern itself; now with the `zap()` termination rule.
- `opcache-inprocess-fork.md` — why workers share opcache (prototype+fork) and why exec'd
  children do not.
- `drupal-cron-queue-stub.md` — the stub's two trigger transports.
- `freeunit-1361-rootless-live-test.md` — the rootless stand this was measured on.
