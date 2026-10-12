# FreeUnit ACME/TLS — Plan (nginx-acme comparison)

**Created:** 2026-08-22
**Status:** PLAN — not started
**Goal:** Native ACME/Let's Encrypt support for FreeUnit
**Source:** comparison of nginx-acme 0.4.1, Unit's existing cert handling,
lego DNS provider landscape

---

## Why not copy nginx-acme

Adopting nginx's approach is possible **in shape** but buys nothing on
wildcards. nginx-acme 0.4.1 (May 2026) still has **no dns-01 and no
wildcards** — open issue #11.

Three of the four mechanisms nginx-acme needs, Unit/FreeUnit **doesn't**:

| nginx-acme mechanism | FreeUnit equivalent |
|----------------------|---------------------|
| worker-0 election | ❌ unnecessary — controller is already a singleton |
| shared memory zone | ❌ unnecessary — same reason |
| variable-cert trick | ❌ unnecessary — Unit already rotates certs connection-gracefully via config re-apply |

The "we have most of the pieces" read was ~70% right. **The missing 30% is
one coherent thing:** resolver + TLS-client transport + a minimal HTTP
client. nginx-acme got the first two free from nginx and wrote the third
itself (~10KB).

## The DNS provider problem — decisive

Numeric reality:

- **lego has 220 providers ≈ 85k Go LOC** — 77% of the entire project.
- Nobody reimplements that in C:
  - Caddy keeps zero in core
  - Traefik embeds lego
  - certbot bundles 13
- **Propagation checking is a whole second subsystem** — lego polls every
  authoritative NS every 2s and follows CNAMEs.

### The one exception: acme-dns

- One-time CNAME collapses all providers to a **3-endpoint REST API**
- ~238 LOC
- Keeps exactly 2 rolling TXT records — specifically for **wildcard+apex
  orders**

## Recommendation ladder

### Days — PUT-overwrite of an in-use cert + auto re-apply

- Kills the rename/repoint/delete dance
- Makes every external client a one-liner
- Fixes upstream #195
- **Prerequisite for everything else — ships value alone**

### Weeks — unit-acme sidecar embedding lego

- Inherits 220 providers and **ARI** for free
- Keeps DNS API credentials out of the daemon
- Leapfrogs nginx: nginx has neither dns-01 nor wildcards

### Later — in-daemon Rust shim (zero-config TLS story)

- http-01 first
- dns-01 only ever as an **acme-dns client**

> Language check (2026-09-25): keep the in-daemon shim in **Rust/C** — http-01 and
> tls-alpn-01 need no DNS providers, so Go/lego's 200-provider breadth is
> irrelevant here. Wildcards (dns-01) are a **Go/lego sidecar**, not in the
> daemon. See `engineering/acme-step3-indame-language.md`.

---

## Key facts to remember

- nginx-acme 0.4.1 (May 2026): no dns-01, no wildcards (issue #11)
- lego = 220 providers, ~85k Go LOC, 77% of project
- Caddy: zero DNS providers in core; Traefik: embeds lego; certbot: 13
- acme-dns: 3-endpoint REST API, ~238 LOC, 2 rolling TXT records
- Unit already rotates certs gracefully via config re-apply (no restart)
- FreeUnit missing: resolver + TLS-client transport + minimal HTTP client
- Upstream #195: cert rename/repoint/delete dance

## Upstream precedent — full issue survey (via `gh_archive`, 2026-09-10)

Searched the **complete** nginx/unit archive (1087 issues + 467 PRs, 2017→2025, repo
archived) offline for ACME/cron/cert. Findings that bear on X9/X10:

| Issue | State | Bearing |
|---|---|---|
| **#424** «Integrated certbot in unit» | OPEN 2020-2026 | The direct X9 request. smtalk: *«certbot supports post-hooks, it could simply load the cert to the unit store»*. Users left for **Caddy** (connebs 2023: *«because of the built-in support for LetsEncrypt»*; raix 2025: *«cert management / TLS-ALPN-01 baked into Unit — one of the biggest drawbacks vs Caddy»*) |
| **#195** «Need a better way to update certificate» | OPEN 2018-2025 | = our **X9 Step 1**. lcrilly confirms the 3-step rotate; MagnusOxlund (2025): *«is the plan for Unit to perform the steps internally, so a single PUT can rotate?»*; `PUT` on an existing bundle → `{"error": "Certificate already exists."}` |
| **#547** «Best practice about certificate rotation» | CLOSED 2021 | mTLS + rotation + **cron** in one thread. sycured: *«1 process: unit; 1 daemon/cron: pulling the new certificate»*. **VBart: «Do you plan to support Mutual TLS? — Yes… like `ssl_verify_client`/`ssl_client_certificate`… likely this year» (2021 → still not shipped)** |
| **#406** «Ability to load multiple certificates» | CLOSED (SNI, 1.23.0) | solved |
| **#1528** «How to run commands alongside applications?» | CLOSED 2025 | **DECISIVE for X10**: user wanted Laravel queue/`schedule` alongside apps; **ac000 (maintainer): «I think this is really outside the scope of Unit»** |
| **#1015** «concurrent jobs in multi-instance Express app» | OPEN | about the *app*, not a Unit scheduler |

→ **Full six-theme survey** (ACME, cert lifecycle, certs API, mTLS, scheduler, TLS-module)
in `engineering/unit-archive-acme-cron-survey.md` — incl. **#307** (peer-cred ancestor),
#358 (ECDSA, open), #659 (prototype lifecycle).

**Reading for the roadmap:**
- **X9 (ACME) + Step-1 (PUT-overwrite) address LIVE upstream demand** (#424, #195,
  #547) with documented user churn to Caddy → strong PR/story value.
- **mTLS is an old unfulfilled upstream promise** (VBart 2021 on #547, same as #225) →
  our D7/X11 mTLS work closes a 4-year TODO.
- **X10 (daemon-internal scheduler) was NOT requested upstream — and was actively
  declined** (#1528: maintainers say running commands/scheduling is out of scope).
  So X10 is **our own differentiator**, not upstream-alignment. Keep it an IDEA,
  framed as "TLS/ACME self-management", not "a general cron".
- **"cron" is absent from Unit history** as a feature request; the ecosystem answer
  is always "external cron/certbot/systemd" (#547 tippexs: *«add a crontab to your
  container image»*).

**Method:** `python3 tools/gh_archive.py search --repo nginx/unit "<term>"`
(zero API calls — see `gh-archive-tool.md`).

## Status & priority (updated 2026-09-06)

**Priority vs Control API auth:** ACME/auto-TLS is the **visible external
differentiator** (what DrupalCon/users see — auto certs, wildcards nginx lacks).
Control API auth is internal hardening (still zero artifacts). For release
readiness, **ACME ladder wins the priority** — but the order is: Step 1 small
(PUT-overwrite) is the prerequisite and ships value alone; Step 2 (sidecar)
is the flagship. Do NOT gate ACME behind Control API auth.

| Step | Effort | Status |
|------|--------|--------|
| PUT-overwrite + auto re-apply | days | NOT STARTED |
| unit-acme sidecar (lego) | weeks | NOT STARTED |
| in-daemon Rust shim | later | NOT STARTED |

## Step 1 technical plan (PUT-overwrite in-use cert + auto re-apply)

**Goal:** make replacing an in-use certificate a one-liner PUT (no
rename/repoint/delete dance, upstream #195).

**I find in the code (verified 2026-09-06):**
- `nxt_cert_info_save()` (`src/nxt_cert.c:428-461`) **does** `lhq.replace = 1` —
  low-level info-store PUT-overwrite by name is present.
- **The store is a DIRECTORY, not an apply-layer pointer.** `nxt_cert_store_load()`
  (`src/nxt_cert.c:922`) does `opendir(rt->certs.start)` + `readdir` — it RE-READS
  the cert files by name on every apply. So replacing a cert at the store level is
  a PUT of the same-named file, which already works.
- **The actual "dance" is the config-upload/apply path**: PUT of a `certificate`
  upload goes through `nxt_controller.c` handlers `nxt_cert_store_get` (1897) /
  `nxt_cert_store_delete` (1912); the LISTENER binding is resolved at re-apply via
  `nxt_conf_get_path(listener, "/tls/certificate")` (`src/nxt_router.c:2249`).
  **The fix is NOT "make store replace" (it already does) but make the listener
  re-apply path swap the served cert on a same-name replacement** — i.e. ensure the
  apply pass re-reads by name (it does load), and that a replacement triggers the
  TLS-listener cert re-config without a manual restart.

**Steps (what to change) — VERIFIED 2026-09-06:**
- `nxt_router_conf_tls_insert()` (`nxt_router.c:2429`) only stores the cert
  **NAME** (`nxt_conf_get_string(value, &tls->name)`) — it does NOT resolve a
  `nxt_cert_t`.
- The resolve is **a single async point**: `nxt_router.c:1267` —
  `nxt_cert_store_get(task, &tls->name, ..., nxt_router_tls_rpc_handler, tls)`.
  When the store returns, `nxt_router_tls_rpc_handler` gets the cert. So a cert is
  resolved ONCE (async) at apply; a same-name PUT does not re-run this.
- **The real fix:** make a same-name cert PUT re-run the listener's
  `tls->name → nxt_cert_store_get` path (re-apply of the TLS listener), so
  `nxt_router_tls_rpc_handler` receives the NEW cert instead of holding the
  cached old `nxt_cert_t`. Store already `lhq.replace=1` + `readdir` by name; the
  missing link is re-resolving by name on listener re-apply after the PUT.
1. **Wire same-name cert PUT to re-apply the affected TLS listener** (re-run
   `nxt_router_conf_tls_insert` + `nxt_cert_store_get`) — single point that
   decides old-vs-new cert.
2. **PUT-same-name = upsert**, and re-resolve by name so the new cert serves on
   the next handshake.
3. **Auto re-apply** — after cert PUT bound to an active listener, trigger the
   re-resolve (Unit already rotates certs gracefully via config re-apply).
4. **Tests:** PUT new cert → 200; PUT same-name replacement → new cert served on
   next handshake (no rename/delete-first); name-collision policy = replace.

**Effort estimate:** days (single coherent slice, not the full ACME client).

## Current status (2026-09-06 refresh)

- **Step 1 verified against code** — the real blocker is the listener cert-swap
  re-apply path (`nxt_router.c:2249`), NOT the store (store is an
  `opendir`/`readdir` dir that already re-reads by name; `nxt_cert_info_save`
  already `lhq.replace=1`). The two quorum models (ling, nemotron-3.5-lightning)
  both flagged the unverified-code SPOT; the verification closes it.
- **Roadmap rows added:** `v1/roadmap.md` now has X9 (ACME/auto-TLS) and X10
  (daemon-internal scheduler) — ACME is no longer off-roadmap.
- **Priority:** ACME/auto-TLS ranks above Control-API auth for release readiness
  (visible external differentiator vs internal hardening). Do NOT gate ACME
  behind Control-API auth.
- **No open ACME PR/issue yet** — this is a plan, not a task. The first
  concrete deliverable would be a PR for Step 1 (PUT-overwrite + listener
  cert-swap re-apply).

## 2026-09-25 update — Step 1 is now in PRs

Step 1 (PUT-overwrite / in-place replace, upstream #195) is implemented as two
PRs in the #438–#469 wave, both by @andypost, labelled "automatic certificates
(ACME, phase 1)":

- **#456** `feat(cert): check the key at upload and reserve dot names` — small,
  no protocol change: `PUT /certificates/<name>` now verifies the private key
  matches the certificate (`X509_check_private_key()`); a wrong-key bundle is
  rejected. Predecessor of #457.
- **#457** `feat(cert): replace a certificate in place through the control API`
  (based on #456) — an external ACME client (certbot, lego) can renew with one
  `PUT`, no downtime, no rename/repoint/delete dance. This is the Step-1 fix the
  plan described (`nxt_router.c` listener cert-swap re-apply path).

Still not started: **Step 2** (unit-acme sidecar embedding lego — 220 providers +
ARI) and **Step 3** (in-daemon Rust shim). Both remain NOT STARTED.

The live-validated thin layer (`acme-certbot-thin-layer.md`) works on top of
Step 1's `PUT`-replace: certbot `--webroot` + `--deploy-hook` → `PUT` the bundle.

## Open questions before Step 1 code

- Does the re-apply path (`nxt_router.c:2249`) cache the `nxt_cert_t` or
  re-resolve by name? If it caches, a same-name PUT won't be picked up until
  restart — that is the "dance" (#195). Verify before writing the fix.
- Is there a test that PUTing the same cert name already returns 200? If the
  control-API upload rejects duplicates, that reject is where the fix lands.


