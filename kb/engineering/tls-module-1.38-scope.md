---
title: TLS as a loadable module — 1.38 scope, gates and checklist
description: The minimal TLS-module slice for 1.38 (core abstraction + loadable module + OpenSSL backend + ALPN owned by the module), its gates and ordering against the h2 stack, what is out of scope (reload, BoringSSL/rustls, isolation), and an actionable checklist.
tags: [freeunit, tls, module, refactor, 1.38, checklist, roadmap]
status: plan
updated: 2026-10-15
resources:
  - https://github.com/freeunitorg/freeunit-exp/pull/23
  - https://github.com/freeunitorg/freeunit-exp/pull/28
  - https://github.com/freeunitorg/freeunit-exp/pull/31
---

# TLS as a loadable module — 1.38 scope, gates, checklist

**Created 2026-10-13 by SOUL.** Window: milestone **1.38**, due **2027-01-29**
(14 open). Evidence: workbench prototypes `freeunit-exp` **#23** (loadable TLS
backend interface, OpenSSL backend, ALPN smoke green), **#28** (connection entry
through the backend table), **#30/#31** (kTLS prototype + measurement); KB
`tls-abstraction-ktls` (variant A ≈ **2–3 weeks**), `tls-module-prototype` (W1).

## Verdict (scope)

Ship in 1.38 the **thin-kernel slice**: core↔TLS abstraction + a **loadable TLS
module** + **OpenSSL as the first backend** + **ALPN owned by the module**.
Everything else (zero-downtime reload, BoringSSL/rustls backends, security
isolation) is **1.39+**.

## In scope (1.38)
- Core↔TLS abstraction wired into `unitd` (loader), OpenSSL as the in-tree backend.
- ALPN (select callback + `conn_alpn_h2`) owned by the module, not the core.
- The module built in the default build (no separate package required to work).

## Out of scope (1.39+)
- Zero-downtime reload (TLS config/listener lifetime — separate design).
- Extra backends: BoringSSL, **rustls** (Rust crypto into a C core — toolchain
  dependency + threading model).
- Security isolation / "core sans TLS data path" — the core keeps `nxt_conn_io`.
- kTLS as a shipping feature (prototype only; orthogonal data-path track).

## Gates / ordering
1. **ALPN ownership** — gates the "thin core" claim. ALPN lives in
   `nxt_openssl.c` today (h2 PR #463). Move it behind the module interface, or the
   core keeps its TLS dependency after the module lands.
2. **h2 sequencing** — the module interface and h2 stage 1 must land in a
   compatible order (interface first, or h2's ALPN written against the module seam).
3. **Interface versioning** — freeze the prototype's `nxt_tls_backend()` + version
   check the loader validates against.
4. **Cert-reload ownership** — core or module (open) — decide before wiring the loader.
5. **Load model** — runtime `dlopen` with a built-in fallback vs a fixed module path
   chosen at configure time (open).
6. **TLS 1.3 no-overlap** — must answer `NOACK` → HTTP/1 on no overlap (open;
   the prototype pins 1.2).
7. **Health/status** — module health to `/status` + the error log.

## Checklist
- [ ] Freeze the module interface (header + version) from the W1 prototype (#23)
- [ ] Decide the load model (`dlopen` + built-in fallback vs fixed path)
- [ ] Decide cert-reload ownership (core vs module)
- [ ] Route the connection entry through the backend table (#28) and land it on master
- [ ] Move ALPN select cb + `conn_alpn_h2` behind the module interface
- [ ] Keep OpenSSL the in-tree first backend; build the module in the default build
- [ ] Resolve TLS 1.3 no-overlap (`NOACK` → HTTP/1) + test
- [ ] Module health → `/status` + error log
- [ ] Rebase h2 stage 1 onto the new ALPN seam (coordinate with `#463`)
- [ ] CI/smoke: ALPN cases (none / `http/1.1` / `h2`) green in the **product** build
- [ ] Docs: module interface + how to build/choose a TLS backend
- [ ] Do-not-claim audit for the 1.38 notes (see below)

## Effort
~**2–3 weeks** of focused work (KB variant-A estimate) **plus** the ALPN/h2
coordination. It competes for the same 1.38 window as h2, schedules (#452), USDT
(#451), status socket, PCRE2 JIT, TLS 1.3/k8s — resource it explicitly, do not
assume.

## Do not claim for 1.38
- "pluggable crypto backends" — only OpenSSL ships.
- "reload TLS without restart".
- "TLS removed from the core" — the core keeps the `nxt_conn_io` data path.

## Verification
- Product build exposes the module loader; ALPN smoke (none / http1.1 / h2) passes
  in CI on the default build.
- No `SSL_*`/`X509_*` call outside the backend module; the core reaches TLS only
  through the interface.

---

## 2026-10-15 — adopter demand signal: SNUnit (Scala Native)

**Source:** lolgab (author of SNUnit, `lolgab/snunit`), posted the ask in the
FreeUnit channel and filed `freeunitorg/freeunit#650` (2026-10-09). andypost replied
points at `docs.freeunit.org/howto/certbot/` and PR **#452** (`schedules`, the
renewal trigger) for 1.38.

**The ask, split into its two real parts — they have different readiness:**

1. **"More of the HTTP stack so it runs without a reverse proxy."** This is
   **browser-facing HTTP/2** (and, later, H3). The stack already exists on the fork:
   PRs #458/#459 (phase 0) → #463 (stage 1, nghttp2 over TLS/ALPN) → #467 (stage 2),
   opt-in `--h2`, 46 tests, ASan clean. It is **sequenced LAST** in the #438–#469
   wave, behind the UAF/lifetime fixes (#414/#415, #425, #464/#465) and the hardening
   stack (#444→#448, #468) — landing it above an unfixed UAF multiplies the blast
   radius (more concurrent streams per connection). H2 at h1-parity body handling is a
   valid MVP; **D3 body streaming is a follow-on, not a prerequisite** (it keeps the
   upload HOL caveat, identical to h1 today).
2. **"Automatic Let's Encrypt like Caddy."** Native ACME, config-driven, HTTP-01
   served by the router, persisted account key, auto-renewal with hot-swap. Two
   readiness tiers (see `acme-tls-plan`, `acme-certbot-thin-layer`):
   - **Ships now, no core code:** the certbot **thin layer** — one HTTP-01 route
     (`/.well-known/acme-challenge/*`) + a deploy-hook that `PUT`s the bundle to the
     Control API. Both halves tested live on 1.36.1. This is the honest answer to
     "HTTPS today" until the native path exists.
   - **Native in-daemon shim:** needs a TLS **client** (to talk to the ACME server) +
     minimal HTTP client + resolver — i.e. the same **X11 hub** the control-socket
     SERVER side (D7) routes through. Renewal needs a **scheduler** (#452 / X10).
     http-01 and tls-alpn-01 need no DNS providers, so this stays **Rust/C in the
     daemon**; wildcards (dns-01) are a **Go/lego sidecar**, never in unitd.

**Why this is a hub event, not a new work item.** Both halves of the ask converge on
**one node — the modular-TLS hub (X11)**:

- H2 needs **ALPN**, which lives in `nxt_openssl.c` today (#463). Gate #1 of this
  scope doc is "ALPN ownership": if ALPN is not moved behind the module seam, the core
  keeps its TLS dependency after the module lands. A browser-facing H2 adopter
  therefore *pulls on the hub from one side*.
- ACME needs a TLS **client** — the *other* side of the same module interface (server
  side = D7 control auth; client side = ACME). Plus the scheduler (#452) for renewal.

So "prioritize TLS" is not "add features"; it is **"land the hub (X11) that ACME-client,
control-API-server and the H2 ALPN seam all route through, in this order."** The adopter
supplies the missing *demand* justification the roadmap row lacked.

**The embedding detail.** SNUnit embeds `unitd` inside the Scala app (single
executable, generated config, observability stack on unitd). That is a distinct
integration shape (app-embeds-daemon), not P4/persistent-worker — noted, not addressed
here.

**Verdict (hypothesis, maintainer's call):**
- The request creates **no new work**; it validates the existing sequence and raises
  confidence in the hub. Recommended order after 1.37.1: **H2 wave first (it is built
  and gated only by the UAF/hardening work), then the TLS hub (X11), with ACME-client
  and D7 as its two consumers.** The certbot thin layer answers #650 immediately with
  zero core change and should be *documented* as the interim, not sold as the fix.
- **Do not** let the adopter's "no reverse proxy" push H3 into the same breath: H3 is a
  separate transport (UDP/QUIC), gated on TLS 1.3 in the module + D3 + a UDP event
  path; it does not ride the H2 stack.

**Do not claim:** native ACME shipped; H2 default-on; "no reverse proxy needed" (H3
absent); any product number.
