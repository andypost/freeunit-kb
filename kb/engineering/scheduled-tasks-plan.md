# FreeUnit Scheduled Tasks (cron-like) — Plan

**Created:** 2026-08-22
**Status:** IDEA — complements ACME plan + modular TLS
**Context:** If TLS becomes a module (tls.unit.so), a scheduler inside the
daemon lets FreeUnit plan its own updates — cert renewal, module swaps,
config re-apply — without external cron.

---

## Why a scheduler

External cron is a second system to deploy and monitor. FreeUnit already
has the event loop, timers, and the config API. A small built-in scheduler
makes it self-contained:

| Use case | Period | Today | With scheduler |
|----------|--------|-------|----------------|
| ACME cert renewal | ~60 days | external certbot/cron | built-in |
| Module rotation (tls.unit.so swap) | manual/alert | manual | scheduled |
| Config re-apply / reload | manual | manual | scheduled |
| Health checks / warmup | minutes | external | built-in |
| Log rotation | daily | external logrotate | built-in |

## Relation to modular TLS

```
tls.unit.so (OpenSSL today, rustls tomorrow)
  + scheduler
    → "renew certs every 55 days" (ACME)
    → "check for new tls.unit.so, reload on CVE alert"
    → zero-downtime module swap
```

The module + scheduler pair makes FreeUnit self-updating for its own TLS
surface without shipping a full auto-updater.

## Design sketch

Config extension (routes/applications level or a new `schedules` object):

```json
{
  "schedules": {
    "cert-renewal": {
      "cron": "0 3 1 * *",          /* monthly 3am */
      "action": "acme/renew",        /* built-in handler */
      "applications": ["default"]    /* scope */
    },
    "module-check": {
      "cron": "0 4 * * *",
      "action": "module/check-update",  /* downloads+validates tls.unit.so */
      "notify": "log|webhook"
    }
  }
}
```

Built-in actions (v1):
- `acme/renew` — triggers the ACME flow (from the ACME plan)
- `module/check-update` — checks upstream package, reports
- `config/reload` — re-applies config
- `app/restart` — graceful app restart

No user scripts at first — only built-in handlers (security: no code exec
from config).

## Security considerations

- Scheduler actions are **built-in only** (no arbitrary command execution
  from config — matches "config is data" principle)
- `module/check-update` must verify signatures (cosign/minisign) before
  swapping a module
- Never auto-swap a module on failure; report and wait
- Credentials (ACME account key) live in the module/sidecar, not config

## X10 — upstream rejection (#1528) and why IPC emulation changes the calculus

**Upstream verdict.** Issue **#1528** «How to run commands alongside "applications"?»
(bitsmyth, 2025-01-07) asked to run Laravel `queue:work` / `schedule:work` inside Unit
and *replace Supervisor* — declaring them as `type: "external"`. Maintainer **ac000**
closed it in 7 days: *«I think this is really **outside the scope of Unit**. … Unit is a
web application server … I think you may have **misunderstood what the external
application type means**. It doesn't mean you can run any random process.»* Author
conceded.

**Why it broke (code-level).** `type: "external"` is not "run this binary". In
`nxt_external.c` `nxt_external_start()`:
- builds an init blob and writes it to the env var **`NXT_UNIT_INIT`**:
  `"<ver>;<stream>;<proto pid,id,fd>;<router pid,id,fd>;<my pid,id,fd_in,fd_out>;<shm_fd,queue_fd>;<shm_limit,request_limit>"`,
- then `execve()`s the binary.
The binary **must** call `nxt_unit_init()`/`nxt_unit_read_env()` (see `nxt_unit.c:529`)
to parse that blob, connect to the router/proto ports, and signal *ready*
(`nxt_router_app_port_ready`, router spins on this). A plain `php artisan queue:work`
never does any of it → the router never sees the app become ready → **config apply
(`curl`) hangs** and the process is untracked → **not stopped on reload**.

**So ac000's objection is precise but narrow:** he rejected `external` **as a generic
process runner**, because `external` implies the *request-serving* libunit contract.

### The counter-argument: the IPC contract is small and emulable

The libunit contract that `external` requires is **not** the full request/response data
path — for a *worker* there are no requests to serve. What's actually mandatory is only
the **registration/readiness handshake** (parse `NXT_UNIT_INIT`, open the ports, say
"ready"). That is a **tiny, public, stable** surface. Therefore X10 does **not** need an
arbitrary-process feature bolted on; it needs a **thin libunit-speaking shim** that:

1. performs the `NXT_UNIT_INIT` handshake once (registers as an app, goes *ready*),
2. then `fork/exec`s and **supervises** the real long-running command
   (queue worker, cron loop, watcher) — restart on exit, forward signals,
3. keeps the port open as a **liveness channel** (heartbeat) so the router keeps it.

This *emulates* exactly the IPC the router insists on, and the worker itself never
learns about Unit. ac000's "must speak libunit" is satisfied **by a shim on our side**,
not by modifying the user's `php`/`node`/anything.

### Why it can "live long" — and the one real trap

Long-lived is already native: the router owns a **prototype process** per app and an
**idle timer** (`nxt_router.c`, `idle_timeout` default **15 s**, `apcf.idle_timeout =
15000`). Prototype-forked processes persist and share opcache (see **#659**).

⚠️ **Trap:** the idle timer reaps apps that stop serving. A queue worker serves nothing,
so a naive shim would be QUIT'd after 15 s. X10 must therefore:
- set the job's `idle_timeout` to **0 / infinite** (or a new `persistent: true` flag),
- and **exclude** job apps from `nxt_router_adjust_idle_timer`'s reap path.

With that, the process lives as long as Unit does — and restarts cleanly on Control-API
reload, which is *more* than Supervisor gives (Supervisor survives only via its own
daemon + config).

### Positioning — do NOT frame as "catching up"

Upstream **deliberately** scoped jobs out (#1528 is a conscious product boundary, not a
missed ticket). So X10 must be sold as a **category extension**, not as fixing an
upstream gap:

| Frame | Verdict |
|-------|---------|
| "Unit forgot a scheduler" | ❌ false — it was declined on purpose |
| "New capability: jobs live in the same runtime as apps" | ✅ — unified isolation/rootfs/user/cgroups/telemetry/logging, one Control API, no separate Supervisor daemon |
| "One config for web + worker" | ✅ — the concrete win over `cron + docker exec + manual env` |

**Concrete competitor = Supervisor / systemd / s6.** The pitch must answer *why not just
run Supervisor next to Unit*: because then you have **two process trees, two configs,
two lifecycles** for one app — X10 collapses them.

### Design consequence

- Build the **shim + `job` app type** (or a `persistent` variant of `external`) that
  satisfies the libunit handshake and supervises a child.
- Reuse router process management (fork/restart/signal) — do **not** write a second
  supervisor inside the daemon.
- Keep **built-in actions only** (see sketch below): no arbitrary code from config.
- Pair with the **`/run` primitive (Phase B)** for one-shot tasks; the shim covers
  long-lived ones.

**Bottom line:** ac000's rejection rests on the IPC contract being mandatory. It is — but
it is small, public, and **emulable on our side**. With a persistent-job flag to defeat
the 15-s idle reaper, in-daemon long-lived jobs are sound. X10 is our differentiated bet,
and the honest story is *"we broaden Unit into jobs,"* not *"we complete upstream."*

## Relation to existing roadmap (andypost/unit)

The scheduler is already in `roadmap/unit-maintainer.md` — not a new idea:

- **Phase B:** scheduler primitive phase 1 (`/run`)
- **Phase D:** scheduler config + overlap policies + retries + status
- **Strategy:** "Scheduler is not a side feature" — running scheduled tasks
  inside Unit unifies runtime, isolation, rootfs, user, cgroups, telemetry,
  logging. Replaces fragile "cron + docker exec + manual env replication"
  setups.
- **Design rule:** features appearing in more than one language roadmap are
  implemented in router/controller/libunit first. Scheduler lives in core.

This KB plan aligns with those phases and adds:
- built-in actions only (no code exec from config)
- module rotation hook (tls.unit.so swap on CVE alert)
- ACME renewal tie-in

## Priority vs other plans

| Plan | Relation |
|------|----------|
| ACME (PUT-overwrite first) | scheduler enables auto-renew |
| Modular TLS | scheduler triggers module swap |
| Config API | scheduler re-applies config |
| Roadmap Phase B `/run` primitive | scheduler is the Phase B/D item |

Scheduler is **after** ACME days-step and modular TLS — it makes both
self-driving. It is not a prerequisite for either.

## Status

| Step | Effort | Status |
|------|--------|--------|
| ACME PUT-overwrite + re-apply | days | NOT STARTED |
| TLS as module | ~1 week | NOT STARTED |
| Scheduler primitive (`/run`) | Phase B | IN ROADMAP |
| Scheduler config + overlap + retries + status | Phase D | IN ROADMAP |

**X10 status:** upstream-rejected (#1528) → differentiation bet, not catch-up. Technical
feasibility (libunit-shim + persistent flag) worked out — see the X10 section above.
