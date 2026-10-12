# Artisan/worker stubs for FreeUnit — generator + live proof

**Date:** 2026-09-11 · **Status:** built + tested live on running unitd 1.36.1
**Tools:** `tools/artisan_stubs/worker_core.py`, `tools/artisan_stubs/gen_stubs.py`

## Goal

Run long-lived Laravel artisan commands (`queue:work`, `schedule:work`,
`horizon`, …) inside Unit's runtime — one tiny **stub per artisan command**,
without patching PHP or the artisan command itself.

## Decisive finding: the stub language must be Python, not PHP

Verified against the shipped `php84.unit.so`:

| Runtime | Boot hook? | Consequence |
|---------|-----------|-------------|
| **Python (ASGI)** | ✅ `lifespan.startup` | a Python app can spawn+supervise a child at boot |
| **PHP SAPI** | ❌ request-driven only; **TrueAsync not compiled** (`async` config rejected, no `*true_async*` symbols in the .so) | a PHP app **cannot** self-host a long-lived worker |

→ So the **supervisor is Python**; the artisan process is its **child**. This is
cryptographically the same trick as the X10 job-shim, now productised per-command.

## What was built

1. **`worker_core.py`** — one shared ASGI app factory. `lifespan.startup` starts
   `_supervise(command)` (spawn + restart-on-exit with backoff); `lifespan.shutdown`
   cancels and kills children. The command can be **any binary** (PHP, Python, …).
2. **`gen_stubs.py`** — for each artisan command emits:
   - `<name>.py` (3 lines: import core, `make_application("php artisan <cmd>")`);
   - a Unit config fragment (`type: python`, `spare: 1`, `idle_timeout: 0`).

## Live test (running unitd, PHP 8.4.25 + Python 3.14.7)

- Generated stubs for `queue:work --tries=3` and `schedule:work` (with a fake
  artisan logger as the command).
- Applied via Control API → `{"success": "Reconfiguration done."}`.
- Observed in `artisan.out`: **START/EXIT pairs repeating — 2 restarts each**,
  i.e. supervision + restart works for both workers simultaneously.
- Added health listeners 8805/8806 → `{"worker":"... artisan queue:work ..."}`.

## Required config (the one gotcha)

```json
"applications": {
  "queue_work": {
    "type": "python", "path": "<stubs dir>",
    "module": "queue_work", "callable": "application",
    "processes": { "spare": 1, "idle_timeout": 0 }
  }
}
```

- **`spare: 1`** — start eagerly (a worker serves no requests; lazy start would
  never fire without a listener).
- **`idle_timeout: 0`** — defeat the router's 15 s idle reaper, else the worker
  is QUIT'd 15 s after boot. (Both nested under `processes`, not top-level.)

## Usage

```sh
python3 tools/artisan_stubs/gen_stubs.py \
    --out /srv/artisan-stubs --config /srv/artisan-unit.json \
    --php-bin /usr/bin/php \
    --commands "queue:work --tries=3" "schedule:work" "horizon"
# then merge the fragment under "applications" and PUT to /config
```

## Caveats / next

- Stub module names are sanitised to valid Python identifiers (`--tries=3` →
  `_tries_3`), else the loader can't import them.
- One worker process per app; scale with `processes`/`spare` (multiple workers).
- Production: close libunit fds to the child (spike `execve`s without it).
- This is the concrete "for each artisan" form of the X10 primitive — pairs with
  the `/run` one-shot primitive and the ACME app (`x10-job-shim-spike.md`).
