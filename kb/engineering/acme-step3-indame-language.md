---
title: ACME Step 3 — in-daemon shim: Rust or Go?
description: Evaluating the language for the in-daemon ACME shim. The decisive axis is challenge scope, not language — http-01/tls-alpn-01 need no DNS providers (Rust is fine); the 200-provider engine (dns-01/wildcards) is Go/lego and belongs in the sidecar, not the daemon.
tags: [acme, tls, rust, go, lego, architecture]
status: analysis
updated: 2026-09-25
resources:
  - https://github.com/go-acme/lego
  - https://github.com/djc/instant-acme
  - https://github.com/nginx/nginx-acme
---

# ACME Step 3 — in-daemon shim: Rust or Go?

Question (from @andypost): Step 3 of the ACME ladder was planned as an
**in-daemon Rust shim**. Should it be **Go** instead?

Short answer: **the language is the wrong axis to decide first — scope is.**
Step 3's job (zero-config TLS in the daemon) is achievable with **http-01** (and
later **tls-alpn-01**), neither of which needs DNS providers. Go's only real
advantage — lego's 200+ DNS providers — applies to **dns-01 / wildcards**, which
is exactly the part that should stay a **sidecar** (Step 2). So Go buys nothing
for Step 3, and costs the daemon a Go runtime.

## What each challenge actually needs

| Challenge | Providers needed | Wildcards | In-daemon viable |
|-----------|------------------|-----------|------------------|
| http-01 | **none** | no | ✅ today |
| tls-alpn-01 | **none** | no | after modular TLS (X11) |
| dns-01 | **200+ provider APIs** + propagation polling | **yes** | ❌ |

Only **dns-01** needs the provider engine — and dns-01 is the *only* path to
wildcards (`*.example.com`). Everything else is provider-free.

## The two ecosystems

**Rust** — `instant-acme` (pure Rust, Tokio + rustls): full RFC 8555, http-01 /
dns-01 / tls-alpn-01, ARI, EAB, profiles, revocation. **But it ships no DNS
provider catalog** — dns-01 is "manual / external program" or acme-dns. `rustls-acme`
/ `tokio-rustls-acme` are TLS-ALPN-01 focused. Precedent: **nginx's own ACME
module (`nginx/nginx-acme`) is written in Rust** (FFI into C nginx; Rust 1.81+,
bindgen, libclang) — and it supports **http-01 only**, no dns-01, no wildcards
(its issue #11).

**Go** — `go-acme/lego` **as a library** (`github.com/go-acme/lego/v5`): 200+ DNS
providers, ARI, wildcards, http-01/tls-alpn-01/dns-01 + propagation polling. The
CLI is a thin layer over the same library. Embedded by Traefik. This is the only
place the 200-provider breadth exists as an importable engine.

### Correction (2026-09-25): lego is a **CLI tool** — you do not embed it

Pointed out by @TuzelKO. lego ships as a standalone binary, and it already has
the exact hook shape the certbot thin layer used. **No custom Go code is needed
for Step 2** — the "sidecar" is simply the **lego CLI + a deploy hook**:

```sh
# v5: one command, `run` obtains or renews
lego run --dns cloudflare -d '*.example.com' -d example.com \
    --deploy-hook /usr/local/bin/lego-unit-hook.sh
```

- **v5 hooks:** `--pre-hook`, `--deploy-hook`, `--post-hook` (`--run-hook` /
  `--renew-hook` renamed to `--deploy-hook` in v5; `renew` merged into `run`).
- The hook receives `LEGO_HOOK_CERT_PATH`, `LEGO_HOOK_CERT_KEY_PATH`,
  `LEGO_HOOK_CERT_PEM_PATH`, `LEGO_HOOK_CERT_NAME` — concatenate cert+key and
  `PUT` to `/certificates/<name>` (the certbot hook, reused verbatim).
- That is the whole Step 2: **lego CLI + ~40-line hook**, same pattern already
  validated live with certbot — plus dns-01, wildcards and ARI for free.

So "embed lego in a Go sidecar" is over-engineering. Compare: certbot (Python)
does http-01 with a 13-provider DNS reach; **lego (Go CLI) does 200+**. The Go
component is a **binary you install and cron**, not code you write or link.

## The cost of Go *inside* unitd

If Step 3 must be in-daemon **and** carry providers, Go means embedding the Go
runtime into the C daemon (`-buildmode=c-shared` / `c-archive`, dlopen). Known
costs, all documented:

1. **Signals.** The Go runtime installs its own handlers: `SIGURG` (async
   preemption), `SIGSEGV` (panic), and it takes over most signals by default when
   embedded — e.g. intercepting **SIGCHLD** crashed host programs
   (golang/go#13042). Unit has its own event loop and careful signal handling
   (its SIGCHLD drives worker reaping); coexistence is fiddly and is a genuine
   regression surface.
2. **Threads / GC.** Go runs its own scheduler threads and a GC heap inside
   unitd; RSS roughly +few MB baseline and the GC does not promptly return memory
   to the OS.
3. **Build matrix.** cgo cross-compilation needs a C toolchain per target; Unit
   builds across many arches/distros incl. musl. This multiplies CI/packaging
   work that Rust (pure static, no cgo) or C does not add.

Rust in-daemon (nginx's model) has none of 1–3: no runtime threads by default, no
GC, no signal hijacking.

## Verdict

- **Step 3 = in-daemon zero-config TLS → keep it Rust (or C).** http-01 and
  tls-alpn-01 need no providers, so lego's breadth is irrelevant here; Rust gives
  clean FFI + the nginx precedent, without importing a second runtime.
- **dns-01 / wildcards → the lego CLI, as an external tool (Step 2), not in the
  daemon.** No sidecar code to write: lego runs, its `--deploy-hook` `PUT`s the
  bundle. Reasons it stays out of unitd: DNS API credentials must not live in the
  daemon; the engine is ~85k Go LOC; propagation polling is a second subsystem.
- **Do not put Go in unitd.** The only way Go beats Rust is by supplying the
  provider catalog — and that is precisely the part that belongs outside the
  daemon.

### If they still want in-daemon + providers

Feasible via Go `c-shared`, and it would collapse Step 2 into Step 3 (one
component, all providers, wildcards). But the price is a Go runtime inside unitd
(signals, GC, threads) plus a cgo build matrix. If wildcards-in-one-binary is a
hard requirement, prefer a **Go sidecar** with a socket — same providers, daemon
stays clean — over linking Go into unitd.

### Practical split (matches the existing plan)

| Layer | Language | Challenges |
|-------|----------|------------|
| In-daemon shim (Step 3) | Rust/C | http-01, tls-alpn-01 |
| Step 2 — **lego CLI + deploy-hook** (no custom code) | Go binary | dns-01, wildcards, ARI |

This is also the honest reading of the ecosystem: Rust owns the *protocol client*
in-process; Go owns the *provider engine* out-of-process.

## Modular orchestration — Unit-owned renew (proposal, @TuzelKO)

Principle: keep Go out of unitd by invoking the ACME tool as a **subprocess (CLI
layer)**; make the tool **pluggable**; let **Unit own the lifecycle** —
periodically trigger renew, detect the cert changed, reload.

Three pieces:

1. **Isolation.** unitd `exec`s the tool; it never links Go. ✅ exactly the CLI
   approach — no cgo, no Go runtime in the daemon.
2. **Modular contract.** The "module" is any ACME client that can *install* the
   result. The common denominator across tools is the **deploy step**:
   certbot `--deploy-hook`, lego (v5) `--deploy-hook`, acme.sh `--reloadcmd`.
   Contract = "run this command; it installs the cert" (via a Control-API `PUT`
   or into the cert store). Any tool that speaks it plugs in.
3. **Unit-owned loop.** Schedule renew + change-detect + reload.

### What already exists vs what is missing

- **Exists:** replacing a cert triggers a graceful reload (a same-name `PUT` —
  Step 1, #456/#457), no restart; the cert store is a directory re-read on apply.
  So *reload-on-change* is solved.
- **Missing: native periodic command execution.** Unit has **no** "run a command
  on a timer". `#452 schedules` does periodic **HTTP requests to an application**,
  not `exec`. And upstream **#1528** ("run commands alongside applications") was
  **declined** by the maintainer ("outside the scope of Unit"). So "Unit
  periodically triggers renew" is a **new primitive**, not a config toggle.

### Two orchestrations

| Model | Trigger | unitd change |
|-------|---------|--------------|
| **Push** | external timer (cron/systemd) runs the tool → deploy-hook `PUT` → reload | none (today's thin layer) |
| **Pull** (TuzelKO) | Unit schedules the command, watches the cert store, re-applies on change | needs the new primitive |

### Options for the missing primitive

- **(a) external timer** — ships today, no daemon change.
- **(b) a narrow cert-lifecycle hook** in Unit (ACME-specific: "run this issuer
  command on this interval, re-apply on change"), **not** a general cron — this
  sidesteps the #1528 scope objection by keeping it to certificate management.
- **(c) extend `#452 schedules`** to a **command target** (today app-requests
  only) — reuses the scheduling machinery already in flight.

### Security

Config-driven command execution is a **new attack surface**. The issuer command
must be settable **only through the root-owned control socket** and must never be
derived from request input. Treat it like a privilege boundary, not a convenience.

**Recommendation:** agree with the direction — the contract is the deploy step,
isolation is the subprocess. The genuinely new bit is the **scheduled-command
primitive**; scope it narrowly to cert lifecycle (or extend #452's scheduler to a
command target) rather than adding a general command runner, which is the part
upstream declined.

### Refinement (@TuzelKO): drop the hook — exit code + self-check

Even simpler: Unit runs the CLI; on **exit 0** it re-scans its own certificates,
compares them, and reloads the ones that changed. **No `--deploy-hook` at all.**

Why this is better: the hook exists only in the *push* model, because the tool had
to reach Unit's Control API itself. In the *pull* model Unit reads the filesystem,
so the contract shrinks to **"a command that writes certificates into a known
directory"** — any CLI works, whether or not it has a hook (certbot/lego's
`--deploy-hook`, acme.sh's `--reloadcmd` all become optional).

Two constraints must be pinned for this to work:

1. **Cert file format / location.** Unit's certificate objects want **privkey +
   fullchain in one PEM**; lego writes `cert.crt` and `cert.key` **separately**.
   Either the command writes the combined PEM, or Unit learns to accept the split
   layout — a cert-store format decision, not free.
2. **Change detection = fingerprint, not mtime**, followed by a **narrow
   re-apply** (re-resolve the cert by name — the Step 1 / #457 machinery), not a
   full config re-apply.

Still required either way: the **scheduled-exec primitive** (Unit must run the
command on a timer). And exit 0 ≠ changed — a renew often no-ops — so the
re-check-and-compare step is mandatory, exactly as noted.

Net: the hook is a *push*-model artifact. The pull model replaces it with a
filesystem read — fewer coupling points, fully tool-agnostic.


