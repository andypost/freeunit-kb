# FreeUnit App-Level Scheduler (cron-like) — research summary

**Created:** 2026-08-31
**Context:** Complement to `scheduled-tasks-plan.md` (daemon-internal). This is the **app-level** scheduler —
running user periodic tasks (drush cron, Laravel `artisan schedule:run`, Celery beat, Sidekiq, Django `manage.py`)
INSIDE Unit, sharing the app's runtime, isolation, rootfs, cgroups, user, and OTel pipeline.

## Two schedulers — don't conflate

| | `scheduled-tasks-plan.md` | **this** |
|---|---|---|
| Task | daemon-internal (ACME renew, module swap, config re-apply) | user app tasks (cron, queue, purge) |
| Actions | built-in handlers only (no code exec) | arbitrary app cmd |
| Audience | FreeUnit self-service | app operator |
| Source | KB, 2026-08-22 | roadmap `unit-cron.md` |

The "embed into all applications" question is about THIS one.

## Target config (drush example)

```json
{
  "applications": {
    "drupal": {
      "type": "php", "root": "/var/www/drupal", "user": "www-data",
      "isolation": { "namespaces": {"mount": true,"pid": true,"network": false}, "rootfs": "/var/www/drupal" },
      "schedules": [
        {"name": "cron",         "cmd": ["vendor/bin/drush","cron"],         "every": "5m", "on_overlap": "skip", "timeout": "5m"},
        {"name": "queue-default","cmd": ["vendor/bin/drush","queue:run","default"], "every": "1m", "on_overlap": "skip"},
        {"name": "nightly-purge","cmd": ["vendor/bin/drush","cache:rebuild"], "at": "0 3 * * *", "timeout": "30m"}
      ]
    }
  }
}
```

One-shot via control API / unitctl:

```console
$ unitctl run drupal/cron
$ curl -X POST --unix-socket /var/run/control.unit.sock \
       http://localhost/control/applications/drupal/run \
       -d '{"cmd": ["vendor/bin/drush","updb","-y"]}'
```

Status: `/status/applications/<app>/schedules/<name>` → last_run / last_exit / duration / next_run / runs_total / failures_total.

## Implementation angles (from roadmap unit-cron.md)

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| 1 | `*-scheduler` process type (new SAPI) | clean separation, leak-proof | cold-start per fire, per-language duplication | fallback engine |
| **2** | **Controller/router scheduler + task callback** | ONE scheduler for ALL languages; warm interpreter; isolation inherited | libunit ABI bump; in-process side-effect risk | ✅ **recommended** |
| 3 | Sidecar synthetic HTTP | smallest diff, no SAPI changes | app must cooperate; auth surface; no raw subcommands | niche |
| 4 | `POST /control/apps/<name>/run` external primitive | trivial, one PR, composable | punts scheduling | ✅ Phase 1 path |

## Recommended path: (4) → (2), with (1) as fallback

- **P1 — `/run` primitive** (~1 week). POC: `POST /control/applications/<name>/run` spawns a one-shot worker reusing the app's isolation. Ships alone, validates spawn plumbing. ← MVP target for DrupalCon 28.09.
- **P2 — In-process scheduler** (~3-4 weeks): `schedules` array, cron parser (`nxt_cron.c`, Vixie subset ~300 LoC), timer wheel (`nxt_timer_t`), status API, overlap policies. Scheduler uses P1 primitive; falls back to (1) for SAPIs without task callback.
- **P3 — Observability/lifecycle** (~2 weeks): OTel span `scheduler.run`, retry backoff, overlap (`skip`/`queue`/`parallel`/`cancel_previous`), timeouts, stdout/stderr tagging, ring buffer.

## Why "all applications" (option 2) is the design rule

`unit-maintainer.md`: *"features appearing in more than one language roadmap are implemented in router/controller/libunit first."* Scheduler lives in core (router/controller), not per-language. SAPIs just implement `nxt_unit_task_handler_t`.

## Cross-cutting decisions

- **Schedule syntax:** interval `"every": "30s|5m|1h"` (preferred/default), cron `"at": "*/5 * * * *"`, `@daily`, `@hourly`, `@reboot`, `"tz"` per-schedule.
- **Time source:** `nxt_timer_t`, not SIGALRM. Catch-up policy `"catchup": "none|one|all"`.
- **Concurrency/overlap:** `skip`(default), `queue`(max_queue), `parallel`(max_concurrent), `cancel_previous`(SIGTERM→SIGKILL). Per-schedule in-memory lock.
- **Timeout:** SIGTERM, grace (10s), SIGKILL. Exit code `timeout`.
- **Isolation:** task inherits the app's ENTIRE isolation block (same namespaces/rootfs/cgroup/user/seccomp) — the real selling point over host cron.
- **Security:** `run` requires same auth as mutating control API; rate-limit 10/min/app; env delta additive; never expose control socket to task.
- **Auto env:** drush `--uri`/`--root` auto-populated from config (fixes classic drush-cron footgun).
- **Failure:** retry `{attempts, backoff, max_delay}`, `on_failure` hook (pager/slack), backpressure `skipped_saturation`.
- **Distributed:** two Unit instances both fire same cron. MVP: "pick one host". Long-term `leader_election`.

## Risks (P2, not P1 blockers)

- libunit ABI bump (option 2) — coordination with every SAPI.
- In-process side effects: leaked globals, opcache poisoning, fd drift.
- `processes: {max:1}` app → scheduled task blocks web (document; recommend separate worker-pool app sharing rootfs).
- WASM/WASI task: cleanest first target for option 1 (tiny cold-start, no SAPI coupling).

## File layout if landed

`src/nxt_scheduler.c/.h` (engine), `src/nxt_cron.c/.h` (parser), `src/nxt_controller.c` (+/run), `src/nxt_conf_validation.c` (+schedules), `src/nxt_status.c` (+schedules), `src/nxt_unit.c/.h` (+task callback), `src/nxt_php_sapi.c` (+impl), `test/test_scheduler.py`, docs.

## Priority vs other plans

| Plan | Relation |
|------|----------|
| ACME (PUT-overwrite) | daemon-internal scheduler enables auto-renew (separate, `scheduled-tasks-plan`) |
| Modular TLS | scheduler triggers module swap (separate) |
| Roadmap Phase B `/run` | scheduler IS Phase B item |
| DrupalCon BoF | P1 `/run` POC = demo-able by 28.09; P2 full = SOON |
