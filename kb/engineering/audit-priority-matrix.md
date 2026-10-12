---
title: "FreeUnit Audit Priority Matrix — Risk, Marketing Value, Execution Order"
description: "Prioritized list of all security/quality audits needed for FreeUnit, with risk register and marketing value assessment"
tags: [freeunit, audit, security, risk, marketing, roadmap]
author: "SOUL bot"
updated: "2026-07-20"
---

# FreeUnit Audit Priority Matrix

**Scope:** FreeUnit v1 (C-core), Buran (Rust), v2 PoC (Rust orchestrator)
**Status:** RESEARCHED — actionable tasks below
**Owner:** andypost / TuzelKO

---

## 1. Audit Candidates — Complete List

| # | Audit Area | Scope | Est. effort | Priority |
|---|------------|-------|-------------|----------|
| A1 | **Control API authentication** | D7 on roadmap. **UNIX socket IS gated** since 1.36.0 (`nxt_controller_check_peer_cred()` `5f795d19` — SO_PEERCRED, rejects non-root/non-euid). **Gaps:** (1) TCP control socket bypasses the gate (`if sa_family != AF_UNIX return OK`); (2) same-UID peers pass; (3) no bearer-token/mTLS. See `control-api-auth-d7.md` + upstream nginx/unit #1315/#840/#225. | ~3 weeks | 🔴 CRITICAL |
| A2 | **Config parser NUL/empty-sink hardening** | Issue #116: embedded NUL in config → C-string memory corruption. Covers all config→json→str conversions outside app options. | ~1 week | 🔴 CRITICAL |
| A3 | **HTTP FSM state-machine coverage** | ~18 states in nxt_h1proto.c, ~0% direct test coverage. Fuzzing exists but no unit/state coverage. | ~2 weeks | 🔴 CRITICAL |
| A4 | **Docker seccomp + capget runtime fix** | ✅ **CLOSED — shipped in 1.37.0** (PR #254 / 275e19a0). Original finding: capget blocked by Docker default seccomp → FreeUnit fails to start as non-root. Known workaround (run as root inside container) but undocumented for end users. | ~1 week | 🔴 HIGH |
| A5 | **Refcount / mmap mutex audit** | Issue #120: incoming refcount bump under mutex before 1.35.6. Potential use-after-free on connection close races. | ~1 week | 🔴 HIGH |
| A6 | **Proxy module: request smuggling / truncation** | Issues #72 (TLS + chunked truncation), #106 (trailer truncation). Chunked encoding is classic smuggling vector. | ~1 week | 🔴 HIGH |
| A7 | **PHP rootfs SIGSEGV (8.5)** | ✅ **CLOSED — shipped in 1.37.0** (issue #256, PR #265 / 7a2bb597, tests #278/#279, guard #279). Original finding: test_php_isolation_rootfs fails with signal 11 on PHP 8.5. 1.36.0 ships with skip. Known isolation breakage. | ~3 days | 🟡 MEDIUM |
| A8 | **Memory safety: general heap/stack audit** | C codebase, no Rust boundary. Areas: connection lifecycle UAF, buffer overflows in JSON→str, nxt_port memory, shared-message queue. | ~4 weeks | 🟡 MEDIUM |
| A9 | **Supply chain / dependency BOM** | OTel staticlib (tokio/hyper/tower via Cargo.lock), wasmtime 36, njs, OpenSSL, libxml, libpcre2. No sbom, no CVE monitoring pipeline. | ~1 week | 🟡 MEDIUM |
| A10 | **Graceful shutdown / signal handling audit** | SIGQUIT new in 1.36.0. Signal → request drain → PID namespace cleanup → respawn-loop protection (part of seccomp plan). | ~1 week | 🟡 MEDIUM |
| A11 | **TLS posture audit** | OpenSSL 3.6 migration pending. No OCSP stapling, no ECH/PQC (D4 on roadmap). ciphersuite audit, cert validation path. | ~2 weeks | 🟢 LOW |
| A12 | **Seccomp at app level** | FreeUnit zero seccomp internally. seccomp-isolation.json planned but not shipped. | ~1 week | 🟢 LOW |
| A13 | **Logging / telemetry info-leak audit** | OTel Phase 0 config audit done. Error messages in alerts may leak paths/configs. Structured logging (D8) planned. | ~3 days | 🟢 LOW |
| A14 | **Fuzzing coverage expansion** | Fuzzing exists (fuzzing/ dir). D10 on roadmap = ~1 week. Currently basic — no structure-aware fuzzing for HTTP FSM. | ~1 week | 🟢 LOW |

---

## 2. Risk Register

| # | Risk | Impact | Likelihood | CVSS-clone | Mitigation |
|---|------|--------|------------|------------|------------|
| R1 | Control socket takeover → full server compromise | CRITICAL — attacker can exec arbitrary code, read files, pivot | HIGH on shared-host/container (localhost access) | 9.5 | D7 roadmap, add auth ASAP |
| R2 | NUL in config → silent memory corruption / RCE | CRITICAL — memory corruption in nxt_conf.c | LOW (requires crafted JSON input to API) | 8.8 | Issue #116, sanitise all str→cstring |
| R3 | HTTP FSM edge → desync / request smuggling | HIGH — request smuggling, cache poisoning | MEDIUM (uncovered states = unknown) | 7.5 | FSM state table + property-based tests |
| R4 | capget EPERM → FreeUnit won't start in Docker | MEDIUM — user can't run in standard Docker | HIGH (every new Docker user hits this) | 6.5 | docs + capget fallback at startup |
| R5 | Refcount race → UAF on connection close | HIGH — UAF, double-free | MEDIUM (race window is narrow) | 7.0 | audit all nxt_ref_get/put pairs |
| R6 | Proxy chunked + TLS → truncated/spliced body | MEDIUM — data corruption | MEDIUM (reproducible at 52 MiB threshold) | 6.0 | fix chunked relay (#72, #106) |
| R7 | PHP isolation broken on 8.5 | MEDIUM — no rootfs isolation for latest PHP | HIGH (all PHP 8.5 users) | 5.5 | fix SIGSEGV in nxt_php_sapi |
| R8 | CVE in deps (wasmtime/otel) | HIGH—CRITICAL depending on dep | LOW (wasmtime CVEs tracked, OTel not) | 6.0 | SBOM + CVE monitoring pipeline |
| R9 | TLS → downgrade / mitm | MEDIUM — trust degradation | LOW | 4.0 | OCSP stapling, ciphersuite audit |
| R10 | No app-level seccomp → compromised app gains full kernel | MEDIUM — container escape after app RCE | LOW (depends on app being compromised first) | 5.0 | ship seccomp-isolation.json |

---

## 3. Marketing Value Per Audit

| # | Audit | Marketing hook | Value to buyers | Monetization lever |
|---|-------|----------------|-----------------|-------------------|
| A1 | **Control API auth** | "Enterprise-ready: authenticated control plane" | Hosters, enterprises deploying in prod | Required for Enterprise SLA tier |
| A2 | **Config parser hardening** | "Rigorously hardened configuration pipeline" | Enterprise customers, security-conscious shops | Security audit as paid consulting |
| A3 | **HTTP FSM coverage** | No direct marketing — internal quality | N/A | Not marketable directly |
| A4 | **Docker capget fix** | "Just `docker run` — works out of the box" | EVERY Docker user. #1 onboarding friction | Removes adoption blocker |
| A5 | **Refcount audit** | No direct marketing — crash prevention | N/A | Not marketable directly |
| A6 | **Proxy module fixes** | "Reliable proxy — no data corruption" | Users proxying to upstream apps | Reliability SLA commitment |
| A7 | **PHP rootfs fix** | "Full isolation on PHP 8.5" | PHP teams using isolation features | Isolation as product differentiator |
| A8 | **Memory safety audit** | "Safety-audited C core" — can claim audit if done | Risk-averse enterprises | Security audit service sell |
| A9 | **Supply chain BOM** | "SBOM-ready — we know what ships" | Compliance teams (SOC2, ISO 27001) | Enterprise SLA add-on |
| A10 | **Graceful shutdown** | "Zero-downtime restarts" (if documented) | Prod deployers | Part of reliability story |
| A11 | **TLS posture** | "Modern TLS: OCSP, ECH, PQC-ready" | Security-minded buyers | Enterprise tier diff |
| A12 | **Seccomp at app level** | "App-level seccomp — defend your server from your app" | Security-conscious ops | Docker premium images feature |
| A13 | **Logging info-leak** | No marketing — compliance fix | N/A | Not marketable directly |
| A14 | **Fuzzing coverage** | "Fuzzed against 10k+ test cases" (if expanded) | Enterprise procurement | Security audit report deliverable |

---

## 4. Execution Order — What To Do First

### Phase 0: IMMEDIATE — ✅ 2 of 3 closed (2026-10-06)
> capget (A4/P0.1) and rootfs (A7/P0.3) were fixed and **shipped in 1.37.0** — kanban Done #17/#18. **Control API auth (A1/P0.2) is the only item still open**, with zero artifacts. Do not quote the rows below as current status.
```
[P0.1] ✅ DONE (1.37.0, PR #254 / 275e19a0) — A4: fix capget fallback for non-root
       Why: blocks every new user. #1 onboarding failure.
       How: make capget EPERM non-fatal → continue without setid capability.
       File: src/nxt_capability.c → nxt_capability_specific_set()
       
[P0.2] 🔴 OPEN — A1: Control API: implement auth
       Why: unauthenticated control = critical vulnerability in shared infra.
       How: D7 on roadmap. Start with bearer-token, add mTLS later.
       
[P0.3] ✅ DONE (1.37.0, PR #265 / 7a2bb597) — A7: PHP rootfs SIGSEGV on 8.5
       Why: isolation tested but broken for latest PHP. Users hit this.
       How: ldd PHP 8.5 → diff rootfs fixture → add missing libs or paths.
```

### Phase 1: NEXT RELEASE (1.37.0 target) — fix known holes
```
[P1.1] A2 — Config NUL/empty sink hardening
[P1.2] A6 — Proxy chunked relay fixes (#72, #106)
[P1.3] A5 — Refcount race audit
```

### Phase 2: WITHIN 2 MONTHS — systematic improvement
```
[P2.1] A3 — HTTP FSM state coverage (unit + property-based tests)
[P2.2] A9 — SBOM + CVE monitoring pipeline
[P2.3] A10 — Graceful shutdown: respawn-loop protection, PID cleanup tests
[P2.4] A14 — Fuzzing: structure-aware for HTTP, JSON config
```

### Phase 3: Q4 2026 — enterprise-grade posture
```
[P3.1] A8 — Memory safety audit (full walkthrough of connection lifecycle)
[P3.2] A11 — TLS posture: OCSP stapling, ciphersuite audit
[P3.3] A12 — Ship seccomp-isolation.json (from seccomp plan §2.2)
[P3.4] A13 — Logging: strip sensitive paths, structured JSON
```

---

## 5. Deliverables

For each audit in execution order:

```
┌────────────────────────────────────────────────────┐
│ A4 — Docker capget fallback                        │
│ Del:   patch to nxt_capability.c + docs            │
│ Test:  Docker default seccomp + non-root unitd     │
│ KB:    update kb-freeunit/engineering/             │
│ Time:  3-5 hours                                   │
├────────────────────────────────────────────────────┤
│ A1 — Control API auth                              │
│ Del:   bearer-token auth on /control/*             │
│ Test:  auth-then-request, bad-token-rejected       │
│ KB:    new doc: control-api-auth.md                │
│ Time:  ~3 weeks                                    │
├────────────────────────────────────────────────────┤
│ A7 — PHP 8.5 rootfs                                │
│ Del:   rootfs fixture update + fix                 │
│ Test:  test_php_isolation_rootfs passes on 8.5     │
│ Time:  ~3 days                                     │
├────────────────────────────────────────────────────┤
│ ...and so on per audit                             │
└────────────────────────────────────────────────────┘
```

## 6. Marketing / Sales Impact

| Action | Impact statement for landing page / pitch |
|--------|-------------------------------------------|
| Fix A4 (Docker) | "FreeUnit runs in standard Docker — no --privileged, no custom seccomp profiles needed for basic operation" |
| Ship A1 (auth) | "Authenticated control plane — bearer token + mTLS support" |
| Ship A9 (SBOM) | "Full software bill of materials available per release — SOC2/ISO-ready" |
| Ship A12 (seccomp) | "App-level seccomp: isolate your application from the kernel — extra defense in depth" |

---

## 7. KB Update Needed

Create new file: `kb-freeunit/engineering/audit-priority-matrix.md`
