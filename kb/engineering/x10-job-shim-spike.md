# X10 job-shim spike — run long-lived jobs inside Unit, and reuse for ACME

**Date:** 2026-09-11 · **Status:** spike DONE (Python prototyped + executed; C
skeleton written, not compiled — no toolchain on the box)
**Artifacts:** `spikes/unit-job-shim/{job_shim.c, job_asgi.py, acme-reuse.md}`

## Goal

Test the X10 counter-argument to upstream's #1528 rejection: that ac000's
objection ("`external` must speak libunit") is satisfiable by a **thin shim on our
side**, so a plain long-running command can live inside Unit's runtime.

## What was built & proven

| Artifact | Language | Status | What it proves |
|----------|----------|--------|----------------|
| `job_shim.c` | C | written, **not compiled** | the canonical form: parse `NXT_UNIT_INIT` → `nxt_unit_init` (handshake) → `ready_handler` forks+supervises the job → `nxt_unit_run` = liveness; `quit` kills child |
| `job_asgi.py` | Python | **executed ✓** | **no C needed** — Unit's native `python` module does the libunit handshake; ASGI `lifespan.startup` IS the ready_handler. Verified: handshake → `lifespan.startup.complete` sent, job spawned, restart-on-exit observed |

**Key result:** the Python path is strictly better on a constrained box (no
compiler, no ~800 MB zig/clang, no libunit.a). It reuses a module Unit already
ships and tests (`test/test_asgi_lifespan.py`). `job_asgi.py` ran a 3.2 s
simulation: emitted `startup.complete`, launched `sleep 1` as a child,
supervised + restarted it, and terminated cleanly on shutdown.

## Code facts confirmed (grounding)

- `src/nxt_external.c` `nxt_external_start()` builds the `NXT_UNIT_INIT` env blob
  and `execve()`s the binary — the app must call `nxt_unit_init()`
  (`src/nxt_unit.c:529`) or the router never sees it become **ready**
  (`nxt_router_app_port_ready`) → config apply hangs, process untracked (#1528).
- ASGI lifespan wired: `nxt_python_asgi.c` → `nxt_python_asgi_startup()` →
  `nxt_py_asgi_lifespan_startup()`; shutdown symmetric. So Python apps get
  startup/shutdown hooks natively.
- **Idle-timer trap confirmed:** `nxt_router.c` `apcf.idle_timeout = 15000` (15 s
  default); `nxt_router_app_need_start()` gates on `active_requests` /
  `spare_processes`. A worker serves nothing → needs **`idle_timeout:0`** and
  **`spare>0`** or it is reaped / never eagerly started.

## Config to run the Python job

```json
"applications": {
  "queue": {
    "type": "python", "path": "/opt/jobs", "module": "job_asgi",
    "callable": "application", "processes": 1, "spare": 1,
    "idle_timeout": 0,
    "environment": { "JOB_CMD": "/usr/local/bin/php artisan queue:work" }
  }
}
```

## Reuse for ACME (see `acme-reuse.md`)

The same primitive hosts the ACME renewal agent: **one app = scheduler + ACME
client + deployer**. `lifespan.startup` starts a `renew_loop`; the loop does ACME
(cert fetch), the challenge, then `PUT /certificates/<name>` over the **unix
control socket** and re-applies (X9 Step 1). It is the hub that finally *uses*
X9 (PUT-overwrite) + X10 (this primitive) + X11 (modular TLS) + D7 (control auth)
together — matching the feature-relationship map in `v1/roadmap.md`.

Two-step ladder: **Step A** HTTP-01 (no TLS work, no X11 dependency) →
**Step B** TLS-ALPN-01 (needs X11 to select a cert per-ALPN during handshake).

## Positioning consequence

Confirms the X10 framing: this is a **category extension** ("jobs live in the same
runtime as apps"), not a completion of upstream. The shim makes upstream's
mandatory IPC contract free — so #1528's rejection no longer blocks us.

## Open items

- Compile `job_shim.c` only where a toolchain exists (Hetzner/Scaleway), not here.
- Next spike (when greenlit): `acme_asgi.py` + self-signed CA round-trip.
- Production must close libunit fds to the child (spike `execve`s without it).
