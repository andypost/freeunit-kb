---
title: Merge plan — FreeUnit PR wave #438–#473 (+ open UAF)
description: Ordered merge plan for the #443 split wave and its follow-ons, with dependencies, conflict pairs, the still-open use-after-free cluster and the decisions to settle before merging.
tags: [release, merge-plan, hardening, uaf, http2, roadmap]
status: active
updated: 2026-09-25
resources:
  - https://github.com/freeunitorg/freeunit/issues/443
  - https://github.com/freeunitorg/freeunit/issues/172
---

# Merge plan — PR wave #438–#473

35 PRs (#438–#473) + the tracking issues. Epic **#443** ("split #437 into small
PRs") covers the first 15 (Steps 1–4); the rest are follow-ons. All open, four
drafts (#463/#467/#470/#471 — the whole HTTP/2 stack plus its fuzz harness). All
by @andypost, AI-generated (cloud Claude Code). Total ≈ **24.7k additions / 1.0k
deletions**.

Live state (checked 2026-09-25 16:53 UTC): all 35 CI **SUCCESS**, all
`mergeStateStatus: CLEAN` — no conflicts anywhere in the wave, including the
#409 / #447 pair. Nothing of the wave has merged yet; master is at `eb1767c9`
(2026-09-20), the last real merges are the 1.35.2 release from April.

Rule: merged top-down. Stacked PRs are *based on* their predecessor, so each
shows only its own diff; once one merges, GitHub re-targets the next to `master`.
Merging out of order forces a manual rebase.

## Phase 0 — independent fixes (base `master`, any order)

Small, no dependencies. Merge when approved + CI green.

| PR | What | Size |
|----|------|------|
| #438 | `compressors` object form accepted (fixes crash #431) | +28/−2 |
| #439 | stop the request deadline at a WebSocket upgrade (fixes #422) | +61/−1 |
| #440 | log a QUIT to an exited worker at info, not alert | +239/−2 |
| #441 | OTel: pass FreeUnit's own span as the app's parent | +180/−25 |
| #442 | Java: binary close reason for an oversized binary message | +81/−1 |
| #454 | `nxt_buf`: do not `memcpy()` from an empty string (UBSan) | +60/−2 |
| #466 | proxy: one `Content-Length` for a chunked request body | +36/−2 |
| #469 | remove the four waived UBSan reports (fix root causes) | +243/−56 |
| #427 | test: release port-ready fixture ports through one helper | — |
| #472 | h1: hold the listener configuration until the TLS connection is freed (TLS shutdown read freed memory after a reconfigure) | +85/−0 |
| #473 | static: close the file before the request pool can go | +12/−7 |

## Phase 1 — hardening stack (merge in this order, stacked)

The application process is untrusted; every value read from shared memory is
bounds-checked before use and read once. Do not reorder.

| # | PR | What | Size |
|---|----|------|------|
| 2.1 | #444 | `--hardening=off\|default\|strict` + `nxt_checked.h`/`nxt_span.h` | +453/−15 |
| 2.2 | #445 | bound reads of untrusted SHM records | +1712/−120 |
| 2.3 | #446 | bound the request/response exchanged with the app | +758/−92 |
| 2.4 | #447 | bound fragment reassembly + release unpaired ports | +571/−3 |
| 2.5 | #448 | bound the retries of the SHM queues | +278/−24 |

Follow-ons that ride on this stack:

| PR | Based on | What |
|----|----------|------|
| #468 | #446 | libunit reads the request from SHM once |
| #455 | #447 | `nxt_process_port_add()` is the only way to pair a port |

**Conflict pair:** #447 and #409 touch the same files (`nxt_port.h`,
`nxt_port_socket.c`). Whichever merges first, the other rebases. #409 is a
pre-existing open PR, not part of #443 — decide its fate in Phase 1.

## Phase 2 — UAF / lifetime (foregrounded: "still a lot of open UAF")

The router→app path still carries use-after-free and dangling-lifetime bugs.
Land these **before** features and **before h2** — h2 multiplies concurrent
streams over the same lifecycle, so it must not sit above an unfixed UAF.

| Ref | Kind | What |
|-----|------|------|
| #414 | issue | epoll/kqueue: a pending fd-event change outlives the port it points into (**UAF**) |
| #415 | PR | drop a port's pending fd-event changes before it is freed — **fixes #414** |
| #425 | issue | `nxt_port_release()` keys teardown off `link.next`; release builds drop the guard (NULL deref) |
| #455 | PR | makes `nxt_process_port_add()` the only pairing path (closes #425 rule) |
| #464 | PR | `nxt_conn_close()` safe for queued I/O handlers |
| #465 | PR | accept / idle-close edge cases (M-4, M-5, M-6, M-11) |
| #408 | PR | pace ENOMEM/ENOBUFS retry instead of spinning (port) |

Umbrella: **#172** — "harden the shared-memory port protocol against a malicious
application process" (kept current; the roadmap for this whole class).

## Phase 3 — CI / tools (after Phase 1)

| # | PR | What |
|---|----|------|
| 3.6 | #449 | ast-grep baseline + **require-tests** gate |
| 3.7 | #450 | non-blocking perf gates |
| 3.8 | #451 | 9 USDT probes behind `--usdt` (zero cost when off) |
| — | #462 | fix C-test leaks; run `build/tests` under ASan+LSan |

**Decision:** #449 — should `require-tests` block from the start, or begin as a
warning? (It gates every other PR, so decide before Phase 3.)

## Phase 4 — features (after Phase 3)

| # | PR | What | Size |
|---|----|------|------|
| 4.9 | #452 | `schedules` — cron-like internal requests, no sidecar | +3890/−72 |
| 4.10 | #453 | Drupal core dev-kit Docker image | +751/−2 |
| — | #456 → #457 | cert: key check + dot names → replace certificate in place (ACME phase 1) | +67 / +821 |
| — | #460 | read-only `/status` socket | +705/−34 |
| — | #461 | match on an absent header/cookie/argument | +200/−10 |

#452 is the largest of the wave — review config format (`docs/schedules.md`,
OpenAPI) → design (`docs/adr/0004-schedules.md`) → code.

## Phase 5 — HTTP/2 (last)

| # | PR | What | Size |
|---|----|------|------|
| p0 | #458, #459 | refactors: validate_host + shared body alloc; neutral field hash | +351 / +262 |
| s1 | #463 (draft) | nghttp2 H2 over TLS/ALPN | +3239/−66 |
| s2 | #467 (draft) | progress timer, lifecycle fixes, limit tests | +1379/−71 |
| s3 | #470 (draft) | graceful drain, flow-control timeout, error matrix, CI (deb/rpm, h2load smoke) | +1572/−108 |
| — | #471 (draft) | libFuzzer target `fuzz_http_h2p` for the h2 frontend, on the real engine + nghttp2 session | +1442/−23 |

The stack is now four deep and strictly chained by base branch:
`master → #463 (feat/h2-stage1) → #467 (feat/h2-stage2) → #470 (feat/h2-stage3)
→ #471 (fuzz/h2p-harness)`. Each PR shows only its own commits; merge them in
that order or the next one needs a manual rebase.

#463 contains #458+#459 in its branch; after those merge, its diff shrinks to the
4 stage-1 commits. Full analysis: `engineering/http2-in-freeunit.md`.

**Decisions before #463:** (a) adopt the nghttp2 build dependency (permanent:
CI + deb/rpm); (b) the h1/h2 content-length divergence (h2 accepts a body without
content-length where h1 → 411).

## Decisions to settle (gate list)

1. **Version split:** current master CHANGES holds 40 entries with 2 Features +
   breaking unitctl changes → patch (1.36.2, security/bugfix) vs minor (1.37.0,
   features/breaking). Decide before tagging.
2. **#449 require-tests:** blocking or warning?
3. **nghttp2 adoption** (Phase 5).
4. **h1/h2 content-length divergence** (Phase 5).
5. **#409 vs #447** — which merges first. Live: both CLEAN/MERGEABLE right now,
   so the conflict is latent, not present — but they still touch the same files
   (`nxt_port.h`, `nxt_port_socket.c`), so whichever lands first, the other
   rebases.
6. **Missing CHANGES entries** the 1.36.x plan found (`start_timeout`,
   `execution_timeout`, wasmtime 43→47, WS UTF-8 1007, …) must be added and
   assigned to a version.

## Review-burden note

~22k lines across 31 PRs, none reviewed by a human yet. The real bottleneck is
review bandwidth and merge order, not regressions: the code is defensive and
additive, breaking changes are few and correct (new refusals instead of silent
corruption), and the new build features are all opt-in (`--hardening` off,
`--h2` opt-in, `--usdt` opt-in) — a default build is unchanged.
