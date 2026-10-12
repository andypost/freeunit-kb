---
title: "FreeUnit v1 Roadmap"
description: "12-month technical roadmap for FreeUnit v1"
tags: [freeunit, v1, roadmap, cross-cutting, php, python, ruby, governance]
resources:
  - "https://github.com/andypost/unit/blob/roadmap/roadmap/unit-roadmap.md"
---

# FreeUnit v1 Roadmap

Consolidated technical roadmap. Source: `roadmap/unit-roadmap.md` in `andypost/unit`.

## Cross-cutting (X) — designed once in router/controller/libunit

| Code | Description | Estimate |
|------|-------------|----------|
| X1 | Unified preload/warmup contract in libunit | ~1 week |
| X2 | Unified status API schema | ~1 week + 3 days/SAPI |
| X3 | Graceful reload endpoint (POST /control/.../reload) | ~2 wks (endpoint), 7-8 wks (full) |
| X4 | Persistent-worker contract (nxt_unit_request_loop_t) | ~3 weeks |
| X5 | Scheduler primitive (POST /run + cron config) | 1-4 weeks |
| X9 | ACME/auto-TLS (PUT-overwrite cert + auto re-apply → lego sidecar → in-daemon) | days → weeks |
| X10 | Daemon-internal scheduler (cert renewal, module swap, config re-apply; pairs w/ X9) | ~2 weeks |
| **X11** | **Modular TLS — move SSL/TLS into a loadable `tls.unit.so` (OpenSSL → rustls). One module serves server-side control-API TLS (D7) + client-side ACME (X9). Keeps the core TLS-dependency-free.** | **~4-6 weeks** |
| X6 | Per-target env/venv overrides | ~1 week |
| X7 | OpenTelemetry span conventions | ~1 week |
| X8 | Metrics endpoint (Prometheus /metrics) | ~1 week |

## Core daemon (D) — language-independent

| Code | Description | Estimate |
|------|-------------|----------|
| D1 | 32-bit ARM alignment (armv7/armhf) | 1-2 weeks |
| D2 | HTTP/2 in router | ~3 months |
| D3 | HTTP body streaming improvements | ~2 weeks |
| D4 | TLS modernization (OCSP, ECH, PQC) | ~2 weeks |
| D5 | Config validation / error messages | ~1 week |
| D6 | JSON Patch / Merge Patch for API | ~2 weeks |
| D7 | Control API authentication | ~3 weeks |
| D8 | Structured logging (JSON) | ~1 week |
| D9 | systemd socket activation | ~1 week |
| D10 | Fuzzing coverage | ~1 week |

## Governance (G)

| Code | Description |
|------|-------------|
| G1 | Supported-versions matrix |
| G2 | Security disclosure process (GHSAs, CVEs) |
| G3 | Release cadence policy |
| G4 | Public CI matrix |
| G5 | Package distribution (APK, DEB, RPM, Homebrew) |
| G6 | Documentation site |
| G7 | Migration guides |
| G8 | Upstream patch triage |
| G9 | Contributor pipeline |
| G10 | Naming/rebranding hygiene |

## Consolidated timeline (12 months)

| Mo | Core | Cross | PHP | Python | Ruby | Gov |
|----|------|-------|-----|--------|------|-----|
| 1 | D1, D5 | X1, X2 | P3 | P2, P3 | P2-P4 | G1, G2 |
| 2 | D9, D8 | X3, X6 | P1, P2 | P1 | P1 | G4 |
| 3 | D4 | X5(p1) | P5 | P4 | P8, P9 | G3, G6 |
| 4 | D6 | X5(p2) | P6, P7 | P7, P9 | P7, P10 | G5 |
| 5 | D3 | X4 | P4 | P5 | P5 | G7 |
| 6 | D2(st) | X7, X8 | P8 | P8 | P6 | G8 |
| 7-9 | D2(sh) | - | P10 | P10 | P11 | G10 |
| 10-12 | D7, D10 | - | P11 | P11 | P13 | G9 |

## Feature relationships (dependency map)

Which features **enable / block / compose** others. Derived from the code (2026-09-10)
and the ACME / scheduler / TLS plan docs. `→` = depends on / enabled by.

### The TLS cluster (X11 is the hub)
```
X11 (modular TLS: tls.unit.so, OpenSSL→rustls)
  ├─ serves → D7  (server-side TLS/mTLS on the TCP control socket)
  ├─ serves → X9  (client-side HTTPS to the ACME CA)
  └─ overlaps → D4 (TLS modernization: OCSP/ECH/PQC live in the TLS backend)
```
- **D7 ← X11**: the TCP control-socket path needs TLS; without X11 that forces OpenSSL on the
  whole core. With X11 it is opt-in. **This is why D7 and X11 must be sequenced together.**
- **X9 ← X11**: ACME is a TLS **client**; `acme-tls-plan.md` names the missing piece as
  "resolver + TLS-client transport + minimal HTTP client". X11 provides the transport.
- **D4 ∈ X11 scope**: OCSP/ECH/PQC are backend features; doing X11 first avoids touching
  14 core files twice.

### The scheduler cluster
```
X5 (scheduler primitive: POST /run + cron config)
  └─ X10 (daemon-internal scheduler) uses X5
        ├─ triggers → X9  (acme/renew)
        ├─ triggers → X11 (module/check-update + zero-downtime swap)
        └─ triggers → X3  (config re-apply / reload)
```
- **X10 ← X5**: X5 is the Phase-B `/run` primitive; X10 is the Phase-D policy layer.
- **X10 ← X11**: the scheduler's "module swap on CVE" action needs the module boundary.
- **X10 ← X3**: `config/reload` reuses the graceful-reload endpoint.

### ACME ↔ D7 ↔ Docker (the decision triangle)
```
ACME (X9)  ── needs ──▶  TLS client  ──▶  X11
D7         ── needs ──▶  TLS server  ──▶  X11
Docker     ── blocks ─▶  unix-only control │ needs TCP+auth ──▶ D7 ──▶ X11
```
- **Docker's blocker is the trigger for D7**: a container reaches the control socket from
  *outside*, needing TCP + auth (upstream #1315). D7 → X11.
- **ACME is the visible differentiator** (`acme-tls-plan.md`: "do NOT gate ACME behind
  Control API auth") — but both share X11, so **build X11 once, feed both**.

### Sequencing implication (proposed)
1. **X11 first** (or alongside) — it unblocks D7 *and* X9's client transport *and* D4.
2. **X9 Step 1** (PUT-overwrite, days) ships value alone, no TLS needed — independent.
3. **D7** on top of X11 (server TLS) — the internal-hardening payoff.
4. **X10** last (scheduler) — composes X5/X9/X11/X3.

### Non-TLS relationships (for context)
- **X4 (persistent workers) → D3 (body streaming)**: both touch the request loop; X4 is the
  contract, D3 is the streaming improvement.
- **X2 (status API) ↔ X8 (metrics)** and **D8 (JSON logging)**: same observability family.
- **A4 (capget/Docker) ↮ D7**: both are Docker-adoption, but capget is *hardening* (KB:
  "severity: hardening, not P0"), while D7/X11 is the real container-control gap.

**Sources:** `engineering/control-api-auth-d7.md` (D7 + X11 + Docker),
`engineering/acme-tls-plan.md` (X9), `engineering/scheduled-tasks-plan.md` (X10 + X11 pairing),
`engineering/rust-toolchain-policy.md` (Rust build toolchain; rustls precedent).

