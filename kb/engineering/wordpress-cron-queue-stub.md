# WordPress cron + Action Scheduler as a Unit app

**Date:** 2026-09-11 · **Status:** built + tested live on running unitd 1.36.1
**Artifacts:** `tools/artisan_stubs/wordpress_stub.py`

## WordPress model = one-shot ticks (like Drupal), two jobs

WordPress has **no built-in worker daemon**. Two scheduling surfaces:

1. **WP-Cron** is a **pseudo-scheduler** — it only fires on a page load, not on a
   real clock. Production pattern: `define('DISABLE_WP_CRON', true)` in
   `wp-config.php` + a real scheduler running `wp cron event run --due-now`.
2. **Action Scheduler** (WooCommerce et al.) is the real **job queue** —
   `wp action-scheduler run` processes a batch and exits (one-shot).

→ Same family as Drupal: **tick scheduler**, not a supervisor. `wordpress_stub.py`
runs **two independent tickers** via ASGI lifespan:
- `wp cron event run --due-now` every `CRON_INTERVAL`;
- `wp action-scheduler run <args>` every `AS_INTERVAL`.

Each ticker **awaits** its run before sleeping → no overlap/stacking.

## Live test (running unitd)

`CRON_INTERVAL=3`, `AS_INTERVAL=2`, fake wp-cli. Observed over ~7 s:
```
cron event run --due-now                          @ :23, :26, :29   (every 3s)
action-scheduler run --batch-size=25 --batches=4  @ :23,:25,:27,:29 (every 2s)
```
Health `:8810/` → `{"cron_interval":3,"action_scheduler":true,"as_interval":2}` ✅

## Config

```json
"applications": {
  "wordpress": {
    "type": "python", "path": "<stubs dir>",
    "module": "wordpress_stub", "callable": "application",
    "processes": { "spare": 1, "idle_timeout": 0 },
    "environment": {
      "WP": "/var/www/html/wp-cli.phar",
      "WP_PATH": "/var/www/html",
      "WP_URL": "https://example.com",
      "CRON_INTERVAL": "60",
      "ENABLE_AS": "1",
      "AS_INTERVAL": "60",
      "AS_RUN_ARGS": "--batch-size=25 --batches=4"
    }
  }
}
```

- **`spare: 1`** — eager start (no listener → never lazily started otherwise).
- **`idle_timeout: 0`** — no-request app → else reaped at 15 s. (Under `processes`.)

## WordPress-specific notes (verified against wp-cli docs)

- **Disable the pseudo-cron**: add `define('DISABLE_WP_CRON', true);` to
  `wp-config.php`, else WP-Cron fires on every page load AND here → double runs.
  The ticker is the *replacement* for that pseudo-scheduler.
- `wp cron event run --due-now` clears the backlog (all overdue events). Use
  `--quiet` to keep logs small; we capture the tail anyway.
- **Action Scheduler** is the correct queue for per-job failure tracking and
  no-data-loss (WooCommerce uses it). Tune with `--batch-size` / `--batches`.
  Set `ENABLE_AS=0` on sites without it (the ticker would just error harmlessly).
- Run wp-cli as the **same user** that owns the docroot (file perms); in a
  rootless Unit setup pass `--allow-root` only if truly required.
- Timing: WP-Cron events have a 1-minute granularity by default → `CRON_INTERVAL=60`
  matches; Action Scheduler wants frequent runs → `AS_INTERVAL=60` (or lower).

## Relation to the other stubs

| Scenario | Stub | Inner loop | Jobs |
|----------|------|-----------|------|
| Laravel `queue:work`/`horizon` | `worker_core.py` | supervise long-lived child | 1 daemon |
| Drupal cron+queues | `drupal_stub.py` | scheduler of drush ticks | cron + N queues |
| **WordPress** | **`wordpress_stub.py`** | scheduler of wp-cli ticks | wp-cron + action-scheduler |
| ACME renew | `acme_stub.py` / certbot hook | scheduled renew + deploy | renewal |

All are ASGI-lifespan apps in the Unit runtime — the X10 primitive applied to
four workloads, same `spare:1` + `idle_timeout:0` requirement, one config, no
host cron, no Supervisor.

## Caveats

- Both WP-Cron and Action Scheduler assume **only one runner** at a time (WP
  locks internally, but overlapping runners waste work). Our await-before-sleep
  tickers guarantee one run per job at a time.
- For multi-worker scale, `processes.max>1` would duplicate the scheduler → keep
  the **stub at exactly one process** (`spare:1`, no `max`) and scale the **web**
  app separately.
