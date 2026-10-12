# Unit archive survey — ACME / cert / mTLS / scheduler

**Source:** local archive of `nginx/unit` (repo **archived** 2025-10-08 → complete,
never stale). Full FTS survey, all branches. **Date:** 2026-09-11.
Tool: `tools/acme_cron_sweep.py` + `tools/gh_archive.py search`.

Method: swept 1554 items + 8590 comments + 2217 reviews for six themes
(ACME/LE, cert lifecycle/rotation, certificates config/API, mTLS/client-certs,
scheduler/cron/jobs, TLS-module/SNI/OCSP), then read the top threads in full.

## Headline findings

1. **No built-in ACME, no built-in scheduler — ever.** Position has been
   consistent for 5+ years: external tooling (certbot / sytemd / cron) + Control
   API. Both are **open, unbuilt feature requests**, not forgotten work.

2. **A working peer-credential mechanism already exists upstream** — PR **#307**
   (i4ki, 2019-09, merged) added `SCM_CREDENTIALS/SCM_CREDS` cmsg to pass
   credentials over the control socket and "IPC validations on obvious places".
   This is the direct ancestor of FreeUnit's `nxt_controller_check_peer_cred()`
   (SO_PEERCRED) gate. Upstream had the primitive since 2019; it did **not**
   ship an auth *policy* on top.

3. **mTLS promised in 2021, still absent.** Maintainer **VBart** on #547
   (2021-05-18): *"Yes. Something similar to the `ssl_verify_client` and
   `ssl_client_certificate` directives in nginx is planned. No ETA yet, but
   likely will be implemented this year."* Five years on, still open (#225).

## Theme: ACME / Let's Encrypt

| # | State | Title | Key signal |
|---|-------|-------|-----------|
| **424** | OPEN since 2020-04 | enhancement: Integrated certbot in unit | The canonical ACME request |
| 195 | OPEN since 2018-12 | Need a better way to update certificate | Rotation = 4-step "dance"; PUT overwrite → `Certificate already exists` |
| 213 | closed | RFE: systemd improvement | Cert reload via systemd, not daemon |

**#424 thread (the strongest external argument):**
- **smtalk** (2020): *"Certbot supports post-hooks, it could simply load the cert
  to the unit store"* → "do it externally" (the project's default answer).
- **connebs** (2023-11): *"I just decided to go with **Caddy** … because of the
  built-in support for LetsEncrypt."* ← measurable churn to a competitor.
- **raix** (2025-02): *"cert management / TLS-ALPN-01 baked into Unit — one of the
  biggest drawbacks compared to Caddy."*

## Theme: cert lifecycle / rotation

- **#195** (open 2018) — the **PUT-overwrite** request == our **X9 Step 1**.
  Current rotation is a manual dance: delete listener-assoc → delete cert → PUT →
  re-attach. Maintainer **lcrilly** (2023-12) confirms the delete-then-add flow.
- **#547** (closed 2021, but the substance is open) — **mTLS + rotation + cron in
  one thread**: user runs *"1 process: unit; 1 daemon/cron: pulling the new
  certificate … bundling … doing the curl"*. tippexs/VBart answer: use
  `docker-entrypoint.d`, s6-overlay, consul-template; no in-daemon scheduler.
  **This is exactly the external-orchestration pattern our X10 proposes to
  internalise.**

## Theme: certificates config/API

- **#406** (closed 2021) — multiple certificates → shipped in **1.23.0** via SNI
  (`listeners` SNI matching). **#484** duplicate, closed.
- **#618** (closed) — "Unknown parameter certificates" (docs/API confusion).
- **#358** (OPEN since 2019-12) — **ECDSA certificate support** missing;
  `PUT /certificates/...` on an EC key → `{"error": "Invalid certificate."}`.
  Still open → relevant to any cert/ACME work.

## Theme: mTLS / client certs

- **#225** (OPEN since 2019-02, 7 yrs) — *Support TLS client side certificates*.
  - **tippexs** (2022-12): *"still a very important feature … would mean we have
    to introduce the SSL Client side in NGINX Unit. This task has not been
    started yet."*
  - **kylecotter** (2024-09): Cloudflare **Authenticated Origin Pull** needs it.
- **#757** (closed, mis-routed) — user asked about disabling OCSP signature
  verification for **client-cert validation**; lcrilly redirected to NGINX.
  Shows real demand for client-cert policy knobs.

## Theme: scheduler / cron / jobs

- **#1528** (closed 2025-01) — **DECISIVE for X10**: user wants to *"replace
  Supervisor"* and run Laravel `queue`/`schedule` long-running commands inside
  Unit. **ac000** (maintainer, 2025-01-13): *"I think this is really **outside the
  scope of Unit**. … Unit is a web application server and as such expects
  certain things."* → **in-daemon scheduler actively rejected upstream.**
  Code-level: `external` requires the libunit init handshake (`NXT_UNIT_INIT`
  env blob + `nxt_unit_init()`), so a plain worker hangs on reload and is
  untracked. **Counter-argument + full X10 positioning:**
  `engineering/scheduled-tasks-plan.md` § «X10 — upstream rejection (#1528) and why
  IPC emulation changes the calculus» (a thin libunit shim emulates the mandatory
  handshake; a `persistent` flag defeats the 15-s idle reaper).
- **#173** (closed) *"Clarify timer and epoll"*, **#64** (closed) *"[timer] set
  timer parent nil after deleted"*, **#659** (OPEN) *Idle timeout and prototype
  processes* — the only "timer" in core is the internal **idle/process-manager
  timer**, never a user-facing cron. **#659** is the prototype-process lifecycle
  thread (fork-from-prototype, PHP opcache sharing) — relevant to our P4 plan.
- **#1041 / #1015** — loopback/background-task confusion in apps; answered
  "external".

## Cross-references (touching 2+ themes)

- **#547** — rotation × certs × scheduler × mTLS (the single richest thread).
- **#195** — ACME × rotation × certs × OCSP.
- **#424** — ACME × rotation × certs.
- **#659** — prototype lifecycle (P4-adjacent), under "scheduler" by keyword.

## Implications for the FreeUnit plan

| Our item | Upstream precedent | Status |
|----------|-------------------|--------|
| **X9 Step 1 (PUT-overwrite)** | #195 (open 2018) | Directly requested; maintainer acknowledges gap → high PR value |
| **X9 (built-in ACME)** | #424 (open 2020), Caddy churn | Long-standing request; strong external argument |
| **D7 (control-API auth policy)** | #307 (peer-cred primitive, 2019) | Primitive exists; **policy/auth on top is our differentiation** |
| **mTLS on TCP** | #547/#225 (promised 2021) | 5-yr-old unfulfilled promise → credibly ours |
| **X10 (in-daemon scheduler)** | #1528 (explicitly rejected 2025) | **NOT an upstream request** — our own bet; frame as new capability |
| **ECDSA certs** | #358 (open 2019) | Blocker to verify before any cert work |

**Bottom line:** ACME (#424) and PUT-overwrite (#195) are **live upstream
requests** our plan addresses. Control-API auth (#307 primitive) and mTLS
(#225/#547) are old promises. The **in-daemon scheduler (X10) is upstream-rejected**
(#1528) — it is our differentiation, not catch-up. Peer-cred is not novel: it
traces to merged PR #307 (2019); our contribution is the policy layer + TCP/mTLS.
