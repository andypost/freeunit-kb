# Drupal cron/queue as a Unit app — the scheduler stub

**Date:** 2026-09-11 · **Status:** built + tested live on running unitd 1.36.1
**Artifacts:** `tools/artisan_stubs/drupal_stub.py`

## Why Drupal needs a DIFFERENT stub than Laravel

| | Laravel | Drupal |
|---|---|---|
| Queue | `queue:work` = **long-lived daemon** (loop inside the process) | `drush queue:run <name>` = **one-shot**: drains items, **exits** |
| Cron | `schedule:work` = daemon | `drush core:cron` = **one-shot**, host schedules it |
| Model | 1 persistent process to **supervise** | frequent short runs = a **scheduler (tick loop)** |

→ Laravel stub = supervisor (`worker_core.py`). **Drupal stub = scheduler**
(`drupal_stub.py`). Same ASGI-lifespan container, opposite inner loop.

## What `drupal_stub.py` does

`lifespan.startup` launches one **ticker per job**:
- `core:cron` → every `CRON_INTERVAL` (default 180 s);
- **one ticker per queue** → `queue:run <q> <QUEUE_RUN_ARGS>` every `QUEUE_INTERVAL`.

Overlap protection is inherent: each ticker **awaits** its run before sleeping,
so a slow cron never stacks up. `queue:run` runs with `--time-limit` so a single
run is bounded — the correct Drupal idiom (`--time-limit`, `--items-limit`,
`--lease-time` are the real knobs).

This is exactly a `crontab` of drush lines, but **inside the Unit runtime**:
no host cron, no Supervisor, one config, unified lifecycle/logging.

## Live test (running unitd)

Config: `CRON_INTERVAL=3`, `QUEUES=cron_queue_test,my_queue`, `QUEUE_INTERVAL=2`.
Observed in `drush.out` over ~7 s:
```
core:cron                                 @ :04, :07, :10      (every 3s)
queue:run my_queue --time-limit=1         @ :04, :06, :08, :10  (every 2s)
queue:run cron_queue_test --time-limit=1  @ :04, :06, :08, :10  (every 2s)
```
Health endpoint `:8809/` → `{"cron_interval":3,"queues":[...],"queue_interval":2}` ✅

## Config (the same two gotchas as every worker)

```json
"applications": {
  "drupal": {
    "type": "python", "path": "<stubs dir>",
    "module": "drupal_stub", "callable": "application",
    "processes": { "spare": 1, "idle_timeout": 0 },
    "environment": {
      "DRUSH": "/var/www/html/vendor/bin/drush",
      "DRUPAL_ROOT": "/var/www/html",
      "CRON_INTERVAL": "180",
      "QUEUES": "my_queue,other_queue",
      "QUEUE_INTERVAL": "60",
      "QUEUE_RUN_ARGS": "--time-limit=55"
    }
  }
}
```

- **`spare: 1`** — start eagerly (an app with no listener is never lazily started).
- **`idle_timeout: 0`** — the app serves no requests → without this the router
  reaps it after 15 s. (Both nested under `processes`.)

## Drupal-specific notes (verified against drush docs)

- **By default Drupal cron already runs queue workers** (`QueueWorker` annotation
  `cron` property; `cron = NULL` opts a worker OUT of cron). So for queues that
  run via cron, you can **skip the per-queue ticker** and just run `core:cron`.
  Use explicit `queue:run <q>` tickers only for queues that opt out (heavy/long
  ones) — that's the standard pattern for big site queues.
- `drush core:cron` should be guarded by `maint:status` (avoid cache poisoning in
  maintenance mode) — add `&& drush maint:status` if needed.
- `queue:run` supports `--time-limit` / `--items-limit` / `--lease-time`.

## When to prefer an OS cron instead

If the site already has a working crontab and you only want the **queue** off the
host scheduler, run just the queue ticker. If you want Drupal **fully self-driven**
inside Unit (no host cron at all), use the cron ticker. Both are supported by the
same app via env.

## Two trigger transports (measured 2026-09-12)

| `TRIGGER` | one tick does | tick latency |
|---|---|---|
| `drush` (default) | spawns a cold one-shot CLI (`drush core:cron`) — PHP start + cold opcache fill + bootstrap **inside the tick** | **0.52 s** |
| `http` | GET on the fork-spawn endpoint; the Unit worker forks a child with **warm** opcache, the tick returns at once | **0.004 s** |

≈130× per tick, and the tick stops blocking: the job continues in the detached child.
`http` mode needs `SPAWN_URL` (`SPAWN_QUEUE_URL` optional, `<q>` placeholder). Every tick
logs its own latency — to `$STUB_LOG`, because a Unit Python app's stdout is not forwarded
to the Unit log. Numbers/method: `fork-spawn-drupal-measurement.md`.

## Queue drain is implemented (was a stub) — measured 2026-09-12

`?job=queue&name=<queue>&limit=<n>` now really drains: `drupal_boot_queue.php` boots the same
`DrupalKernel`, takes `\Drupal::queue($name, TRUE)` (reliable — `claimItem()` needs it), runs
`plugin.manager.queue_worker->createInstance($name)->processItem($data)` per item and
`deleteItem()`s it, with an item limit. Env: `QUEUE_NAME`, `QUEUE_LIMIT`, `QUEUE_FILL`
(fill instead of drain), `DRUPAL_QUEUE_BOOT`; one JSON line per run into `queue_boot.out`.

Real numbers (harness module `fu_queue_test`, 1 ms/item, 50 items): cold CLI 0.26–0.31 s,
real `drush queue:run` 0.67–0.69 s, warm fork child 0.177–0.203 s with the trigger returning
in 3.4–7.2 ms. Method and caveats: `fork-spawn-drupal-measurement.md`.

The site's own `queue:list` is empty on a minimal profile — a queue to measure needs a module
that declares a `#[QueueWorker]` (core: `locale`, `media`, `package_manager`, tests:
`cron_queue_test`).

## Relation to the other stubs

| Scenario | Stub | Inner loop |
|----------|------|-----------|
| Laravel `queue:work` / `horizon` | `worker_core.py` | supervise long-lived child |
| Drupal cron + queues | `drupal_stub.py` | schedule one-shot drush ticks |
| ACME renewal | `acme_stub.py` / certbot hook | scheduled renew + deploy |

All three are ASGI-lifespan apps in the Unit runtime — the X10 primitive applied
to three very different workloads. Same `spare:1` + `idle_timeout:0` requirement.
