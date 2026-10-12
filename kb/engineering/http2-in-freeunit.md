---
title: HTTP/2 in the FreeUnit C core (post-Buran)
description: Deep analysis of PRs #458/#459 (phase 0), #463 (stage 1), #467 (stage 2) — nghttp2-backed HTTP/2 over TLS/ALPN; cost, dependency, gaps and strategic verdict now that Buran is not the edge.
tags: [http2, nghttp2, alpn, tls, router, roadmap, buran]
status: analysis
updated: 2026-09-25
resources:
  - https://github.com/freeunitorg/freeunit/pull/463
  - https://github.com/freeunitorg/freeunit/pull/467
  - https://github.com/freeunitorg/freeunit/pull/458
  - https://github.com/freeunitorg/freeunit/pull/459
---

# HTTP/2 in the FreeUnit C core

Trigger: the plan to terminate H2/H3 in Buran (front-proxy, BWP to FreeUnit) is
dead — *"буран не взлетел"*. The alternative in `strategy/freeunit-2-3-vision.md`
(H2/H3 terminated in a front proxy) therefore loses its in-project champion, and
the fork's own `roadmap D2` ("HTTP/2 in router") becomes the only path to a
browser-facing H2 without an external proxy.

This documents the implementation that exists on the `andypost/unit` fork and is
proposed upstream as PRs #463/#467, and re-evaluates it against the 2026-09-13 KB
estimate.

## Stack shape

Four PRs, all by @andypost, AI-generated (cloud Claude Code), none merged:

| PR | Role | Size |
|----|------|------|
| #458 | phase 0: export `nxt_http_validate_host()`, factor out body alloc — no behaviour change | +351 / −59, 8f |
| #459 | phase 0: protocol-neutral request field hash — no behaviour change | +262 / −2, 8f |
| #463 | **stage 1**: nghttp2 H2 over TLS/ALPN | +3239 / −66, 24f |
| #467 | **stage 2**: progress timer, lifecycle fixes, limit tests | +1379 / −71, 6f |

Dependency order: #458 and #459 are independent; #463 is based on both; #467 is
based on #463. Total ≈ **5.2k additions / 0.2k deletions**.

## What stage 1 (#463) actually is

- New frontend module `src/nxt_h2proto.c` (**+1791**) + `nxt_h2proto.h` (+130).
- **ALPN** select callback (`h2`, `http/1.1`) added in `src/nxt_openssl.c` (+61).
  The 2026-09-13 KB note "no ALPN anywhere in the tree" is now outdated by this PR.
- `nxt_h1proto.c` **−61 net**: h1 body-alloc moved out to shared code.
- `nxt_http_request.c` (+83): shared `nxt_http_request_body_alloc()`.
- `src/nxt_conf_validation.c` (+7): listener option `"tls": {"http2": true}`; the
  validator refuses it when Unit is built without nghttp2.
- `auto/h2` (+67) configure probe; new `--h2` switch (opt-in, requires `--openssl`,
  like `--openssl` itself). Without `--h2`, `nxt_h2proto.c` is not compiled.
- **Each h2 stream is a normal `nxt_http_request_t`** → routing, static files,
  apps, proxy, access log, compression reuse the h1 code unchanged.
- TLS-only, **no h2c** (browsers do not use cleartext h2 anyway).
- Limits: 128 streams, 256 KiB stream / 1 MiB connection window, 1000 requests per
  connection, RST rate limit, 8 CONTINUATIONs, 32 SETTINGS, header list limit →
  **431**. `max_body_size` → **413**. `:authority` validated as Host (400); a
  `host` mismatch resets the stream. `:path` normalized by the h1 parser.
- Tests: `test/test_http2.py` (15 in stage 1, +31 in stage 2 = 46), 3 new C tests.

## Stage 2 (#467) — what it fixes

- One **progress timer per connection**: `header_read_timeout` while a header
  block is incomplete, `body_read_timeout` while only body DATA is owed; HEADERS/
  DATA/chunks reset it, PING/WINDOW_UPDATE/SETTINGS/PRIORITY/CONTINUATION do not.
  Expiry → GOAWAY(NO_ERROR).
- Bugs stage 1 carried, found by the new tests: router crash on 1000 reset streams
  in one read (nghttp2 session deleted inside `mem_recv`), 413 crash (NULL ready
  handler at END_STREAM), missing GOAWAY on fatal nghttp2 errors, hang on
  session-end with streams attached, premature response → RST_STREAM(NO_ERROR),
  leak on `mem_send` failure.
- Bug: `nxt_h1p_peer_connect()` read `r->proto.h1` for h2 requests → any proxied
  h2 request hung/crashed. Fixed to take the connection from the h2 session.

## Cost vs the 2026-09-13 KB estimate

The KB said: not a "few weeks" item — a new protocol module (frames, HPACK, stream
state, flow control) + ALPN + config surface; ~3 months one dev, ~1.5–2 months
AI-assisted for an MVP. **That matches what landed**: a new module (~1.9k lines),
ALPN added, a config surface, staged. The AI-assisted estimate was accurate; ~4
stages were scoped, 2 are proposed.

## Open tension: the D3 prerequisite

The KB named **request-body streaming (D3)** a *hard prerequisite* — without it a
large POST parks on H2 flow control until the body is buffered and the
head-of-line problem reappears one layer up. **#463 does not implement D3**: bodies
are buffered to memory/temp file, honouring `max_body_size` — i.e. h1-parity body
handling.

Consequence: the H2 MVP delivers **stream multiplexing** (the win for GET-heavy
static/API traffic) but keeps the upload HOL caveat. This is *not* a regression
(identical to h1 today) but it is the ceiling of the MVP. Decision point: does D3
precede or follow H2? See verdict.

## Behaviour divergence needing a decision

h2 accepts a body with **no content-length even with `chunked_transform` off**,
where h1 answers **411**. The PR flags this as "needs a decision". Two coherent
H2-native options: accept it (H2 has no chunked TE; DATA frames are self-delimiting)
or keep the 411 for parity. Whichever is chosen must be documented.

## Gaps (not bugs — declared next stages)

- **Stage 3:** GOAWAY notice on reconfigure with streams in flight; deterministic
  cleanup on shutdown; error matrix under ASan; **CI packages (`libnghttp2-dev`)
  and deb/rpm dependencies**.
- **Stage 4:** h2spec, a fuzz target, OpenAPI docs, changelog.
- **Missing features:** trailers (dropped for now), WebSocket over h2 (RFC 8441),
  per-listener limits, no timer for a stream blocked on a closed flow-control
  window. Streams arriving after GOAWAY get INTERNAL_ERROR, not REFUSED_STREAM.

## Dependency / build

- New external dependency **nghttp2** (mature C library; also behind curl).
  Opt-in `--h2`, requires `--openssl`.
- Packaging burden is real: `libnghttp2-dev` in CI (stage 3) and a runtime dep in
  deb/rpm. A new build dependency in the C core is a repo-level decision, not a
  detail.

## Strategic verdict (post-Buran)

1. **The approach is sound and is now the cheapest viable path to browser H2.**
   With Buran out, "terminate H2 in Buran" is gone; the remaining alternative is
   an external proxy (nginx) — acceptable only where one already exists. For
   adopters who want H2 straight from FreeUnit, this stack is it.
2. **Risk to ship is low.** Opt-in flag, no default-build change, staged, heavily
   tested (46 h2 tests + ASan/UBSan clean), no behaviour change for h1.
3. **It closes the #1 documented adoption blocker** (operators churned off upstream
   over missing H2/H3; nginx/unit #388 open since 2020, ice-boxed).
4. **It does not touch H3.** H3 replaces the transport (UDP/QUIC, ~4–6 months after
   D3, and realistically after H2); unrelated to this stack.

### Recommendation

- Accept the H2-in-core path; keep it **opt-in** until stages 3–4 land (packaging
  + h2spec), then consider making `--h2` a distro default.
- **Sequence:** merge phase 0 (#458, #459) → stage 1 (#463) → stage 2 (#467);
  fix the h1/h2 content-length divergence before stage 1 merges; treat **D3 as
  follow-on**, not prerequisite — H2 at h1-parity body handling is a valid MVP.
- **Decide the dependency:** adopting nghttp2 is a permanent build/test/packaging
  commitment. Confirm it is wanted before stage 1, because reverting it later is
  a breaking packaging change.

## Sequencing in the #438–#469 wave

H2 sits at the **end** of the wave, not the front. Two hard reasons:

1. **UAF / port-lifetime work must land first.** The wave carries still-open
   use-after-free and lifetime bugs on the router→app path — `#414` (a pending
   fd-event change outlives the port it points into; fixed by `#415`), `#425`
   (port release keys teardown off `link.next`, guard dropped in release), and
   `#464`/`#465` (connection close with queued I/O handlers). `nxt_h2proto.c`
   hangs off the same connection and request lifecycle, so landing it above an
   unfixed UAF would inherit the bug and multiply the blast radius (more
   concurrent streams per connection).
2. **The hardening stack (#444→#448, #468) bounds everything read from shared
   memory.** H2 adds per-stream parsing on top of that path; it depends on the
   bounds being in place, and its own limits (header list → 431, stream caps)
   assume the shared read-once discipline established there.

Ordering rule: phase 0 fixes → hardening stack → UAF/lifetime fixes → CI/tools →
features → **h2 last**. Full wave plan: `engineering/pr-wave-438-469-merge-plan.md`.

## Comparison pointers

- Buran frontend (dead): Internet → Buran (H2/H3) → BWP → FreeUnit.
- This stack: Internet → FreeUnit `nxt_h2proto` (nghttp2, ALPN) → same
  `nxt_http_request` → same apps.
- FU3 vision puts H2 as a **protocol plugin in the Rust router** — a different
  implementation site. If FU3 is the long-term target, this C core work is the
  bridge until then.
