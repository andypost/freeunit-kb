# TODO.md staleness audit — 2026-09-16 (FreeUnit)

Audited against `origin/master` = `df9843b0` (2026-09-15). File in repo root, 748 lines.
Last substantive edit `34df4fe1` (2026-06-15); only later touch `9d40631a` (2026-08-30, deleted
the PHP 8.5 rootfs SIGSEGV section). 198 commits landed between 2026-06-15 and HEAD.

## Verdict

Content is a June plan. The whole release frame it was written in is gone: it plans
1.35.6 / 1.35.7 / 1.35.8, none of which exist. Actual sequence: 1.35.5 (29 May) →
1.36.0 (16 Jul) → 1.36.1 (28 Aug).

## Section-by-section status

| Section | TODO says | Reality at HEAD | Action |
|---|---|---|---|
| Release roadmap table | 1.35.6 (25 Jun), 1.35.7 (31 Jul), 1.35.8 (28 Aug) | No such releases; 1.36.0/1.36.1 shipped | rewrite |
| "Now (June)" + "Open questions (before August)" | pending | all past-due | rewrite |
| Rust DX: `rust1.x` Dockerfile | step 1 of roadmap | absent — 0 rust Dockerfiles in `pkg/docker/` | re-date or decide |
| Rust DX: `libunit-rust` | step 2 of roadmap | absent, no dir, not on crates.io | re-date or decide |
| OTel — semconv attrs, app-aware spans, missing std attrs, `setError` | open ("1.35.6 remaining") | **done** — 11 keys in `src/otel/src/lib.rs`: `http.request.method`, `url.path`, `url.scheme`, `network.protocol.version`, `user_agent.original`, `server.address`, `client.address`, `http.response.status_code`, `http.request.body.size`, `unit.application.name`, `unit.application.type`; `nxt_otel_rs_set_error` present | tick, re-label 1.36.0 |
| OTel — tracestate to Rust SDK | open | **done** — forwarded in `nxt_otel_parent_context` (`src/otel/src/lib.rs:549-554`) | tick |
| OTel — span leak on aborted requests | open | **done** — span bound to request pool via `nxt_mp_cleanup(nxt_otel_span_pool_cleanup)` (`src/nxt_otel.c:534`) | tick |
| OTel — new config fields (`service_name`, `headers`, `root_certificate`, `resource_attributes`, `max_queue_size`, `export_timeout`) | open | still open — validator accepts only `endpoint`, `batch_size`, `protocol`, `sampling_ratio` | keep |
| OTel — `$otel_trace_id`/`$otel_span_id` variables | open | still open — no hits in src/ or test/ | keep |
| OTel — TLS to collector, metrics | open | still open | keep |
| PHP TrueAsync, items 1-6 | "branch php-graceful-shutdown", struct fields missing, extension missing | branch gone; code on master behind `#if NXT_PHP_TRUEASYNC`; `nxt_php_extension.c` still missing (call at `src/nxt_php_sapi.c:232`, no definition anywhere); no `shutdown_timeout` option; fixtures + `test_php_trueasync.py` still TDD/auto-skip | rewrite: merge #1+#2, drop branch, keep shutdown semantics |
| OpenSSL 3.6 checklist | open | **done** — CI builds OpenSSL 3.6.2 in a stable `/opt/openssl-3.6` slot, plus an OpenSSL 4.0.2 leg; clang-ast job runs `debian:testing` + `--openssl` | close |
| PHP 8.5 `disable_classes` | open | still open — tests still `pytest.skip('disable_classes removed in PHP 8.5')`; also the TODO names `src/php/nxt_php_sapi.c`, real path is `src/nxt_php_sapi.c` | keep + fix path |
| PHP 8.5 rootfs SIGSEGV | open | already deleted 2026-08-30 (fixed by tzdb provisioning, PR #265) | done |
| packages.freeunit.org download stats | open | still open — `https://packages.freeunit.org/stats/` → 404 | keep |
| Prebuilt `fake_upstream` | open | still open — `cargo build --release` in `test/run-local.sh:253` and `build-test.yml:484`; mirror publishes no binary | keep |
| Prebuilt clang-ast image | open | still open — `run-local-full.sh` still builds `freeunit-test-full:local` locally | keep |
| avahahn/ngx-testing-fmk | "decision: no code to borrow" | closed decision, dead weight | delete |
| ngx-rust, ideas 1-3 | open | untouched; idea 1 partly moot (otel crate already 0.32) | trim/merge |
| Chunked encoding (`pre-1.35.5-i58`) | "implemented, pending upstream" | shipped in 1.35.5 as `chunked_transform` (`settings.http`, no longer experimental) and it fixed #58 | delete |
| proxy request buffering (#58) | open design questions | superseded by `chunked_transform` in 1.35.5 (chunked → Content-Length + injected CL) | delete or reframe |

Mirror check: pins and published tarballs agree — njs 1.0.1, wasmtime 43.0.1,
wasi-sysroot 27.0, libunit-wasm 0.5.0.

## Effect of the open PR queue (2026-09-16)

12 open PRs, +6540/−299 lines total; 8 drafts (`410 409 408 406 385 196 99 93`),
4 ready (`405 393 386 144`), 4 conflicting (`410 386 385 196`). None of them edits
TODO.md or references a TODO item; PR bodies contain no OTel / TrueAsync / rust1.x /
libunit-rust / packages.freeunit.org / clang-ast / official-images keywords.

| PR | State | Lane | TODO lines closed |
|---|---|---|---|
| 405 | ready | router: detached worker counted, `/status` detached + openapi | 0 |
| 393 | ready | port: queue wake-up kept when kernel send fails | 0 |
| 386 | ready, conflict | http: range refused after identity rejected (compression) | 0 |
| 144 | ready | security: GHSA backport to 1.34 LTS branch | 0 (TODO has no LTS lane) |
| 410 | draft, conflict | detached worker idle-walk guard + retry budget | 0 |
| 409 | draft | port: bound queued messages holding a descriptor | 0 |
| 408 | draft | port: pace ENOMEM/ENOBUFS retry | 0 |
| 406 | draft | test: suite off fixed `*:8080` (32 files) | 0 |
| 385 | draft, conflict | proxy: consume upstream 1xx interim responses | 0 |
| 196 | draft, conflict | access log: `json` format shorthand (D8-adjacent) | 0 |
| 99 | draft | ci: Trivy filesystem audit | 0 |
| 93 | draft | docs: AGENTS.md + CLAUDE.md (contains `--otel` snippet) | ~3 lines (CLAUDE.md doc gap) |

Merging the whole queue therefore moves TODO.md from 729 to ~726 lines: **−3**.

## Priority mismatch (KB v1/roadmap, strategy NOW/SOON/LATER)

- NOW (Q3 2026): P2 PHP status API, X1 preload, X4 persistent-worker contract,
  P4 PHP persistent worker, prototype+fork opcache, D3 body streaming, X3 graceful reload.
  TODO covers only TrueAsync (the X4/P4 blocker) and partly #58 (D3). Graceful reload (X3,
  SIGQUIT shipped in 1.36.0) and PHP status API (P2) are absent from TODO entirely.
- SOON (Q4 2026): X2 status schema, P2 for other languages, X8 `/metrics`, D8 JSON logs,
  D6 JSON Patch. TODO has one "metrics exploration" line; JSON logs appear only as draft PR 196.
- Off-priority (growth plan of June, nothing started): Rust DX (`rust1.x`, `libunit-rust`),
  packages.freeunit.org stats + prebuilt binaries, Docker Hub official images, avahahn, ngx-rust.

The PR queue and TODO.md are near-disjoint: the queue works the core/security/status lane,
TODO lists the growth lane. That is the structural reason TODO drifted.

### Shrink budget (measured on master, 729 lines)

| Cut | Lines |
|---|---|
| dead / already shipped (OpenSSL 3.6, avahahn, chunked, #58) | −90 |
| OTel: keep only open items (config fields, trace-id vars, TLS to collector, metrics) | −142 |
| roadmap table + "Now (June)" plan | −36 |
| TrueAsync: merge items 1+2, drop branch framing | −94 |
| ngx-rust ideas folded into Rust DX | −65 |
| optional: park Rust DX as one-line LATER entries | −68 |
| **effect of merging all 12 open PRs** | **−3** |

Result: ~300 lines, or ~230 if Rust DX is parked.

## Gaps — what TODO.md does not mention

- No next milestone after 1.36.1 (1.37.0?) and no dated plan.
- 1.36.1 security content (router SHM geometry validation, libunit chunk bounds,
  SCM_RIGHTS replay) is not referenced as "shipped".
- Recent master stream (compression state per configuration, port descriptor ownership,
  weak ETag validators, unitctl JSON5 removal, GnuTLS/CyaSSL/PolarSSL backend removal,
  njs 1.0.1, Cargo.lock audit gate) is absent.
- `EOL.md` exists as the support matrix; TODO duplicates no part of it, but the
  rootfs/disable_classes items are really EOL-driven.

## Editing rules that keep it from drifting again

- Date every milestone claim, or use no dates at all.
- Mark shipped items with the release that shipped them (`1.36.0`, `1.36.1`), never a
  planned version.
- One section = one open decision; delete sections whose decision is already made.
- Verify claims against `CHANGES` + `git tag` before adding a milestone row.
