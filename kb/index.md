---
title: "FreeUnit Knowledge Base"
description: "Complete knowledge base for FreeUnit — Community LTS fork of NGINX Unit"
format: "open-knowledge-format-v1"
updated: "2026-09-16"
maintainer: "andypost"
---

# FreeUnit Knowledge Base


- [history](history) — Project timeline: Igor Sysoev 2017 → F5 → FreeUnit revival → 1.36.0/1.36.1
- [repos](repos) — Repositories and forks (freeunitorg, andypost/unit, Tavern)
- [engineering/freeunit-harness-public-toolkit](engineering/freeunit-harness-public-toolkit) — `freeunitorg/freeunit-harness` (public, 2026-10-10): 9 skills, 7 agent briefs, 22 docs, 39 tools, authority table; check-public gate verified clean on our workbench content


- [v1/overview](v1/overview) — FreeUnit v1: Community LTS fork
- [v1/release-1356](v1/release-1356) — Release 1.35.6 (2026-07)
- [v1/release-1361](v1/release-1361) — Release 1.36.1 (2026-08-29) — graceful shutdown, OTel 0.32, njs 1.0, OpenSSL 4.0
- [v1/roadmap](v1/roadmap) — FreeUnit v1 roadmap (12-month, X/D/G/P items) + feature-relationship dependency map (TLS/scheduler/Docker clusters; X11 modular-TLS hub)
- [v1/architecture](v1/architecture) — FreeUnit v1 architecture (C, multi-process, event loop)


- [v2/overview](v2/overview) — FreeUnit v2 PoC: Rust + NTS PHP
- [v2/architecture](v2/architecture) — v2 architecture: Rust orchestrator + UDS IPC
- [v2/liveness](v2/liveness) — Liveness Monitor: TGID invariant + PING/PONG
- [v2/kpis](v2/kpis) — KPIs and Definition of Done v2


### Performance & io_uring
- [io-uring-ab-benchmark-approach](engineering/io-uring-ab-benchmark-approach) — io_uring A/B benchmarking harness (PR #32)
- [fix-recv-tier-kernel-6](engineering/fix-recv-tier-kernel-6) — Fixing RECV tier constraints on kernel 6.0+
- [io-uring-distro-availability](engineering/io-uring-distro-availability) — Per-distro io_uring availability matrix (kernel tier vs distro policy vs container seccomp); RHEL/EL default to `io_uring_disabled=2`, Docker/containerd block `io_uring_setup`; measured EPERM inside our own container
- [event-loop-alternatives](engineering/event-loop-alternatives) — What to do instead of io_uring: EPOLLEXCLUSIVE/sendfile already present; absent `SO_REUSEPORT`, `recvmmsg`/`sendmmsg`, `MSG_ZEROCOPY`/`TCP_ZEROCOPY_RECEIVE`, `splice`, kTLS; then thread-per-core + BWP kernel dispatch + persistent workers; libuv's own io_uring retreat as the reference point
- [tls-abstraction-ktls](engineering/tls-abstraction-ktls) — TLS out of the core: current `nxt_tls.h`/`nxt_openssl.c` inventory (vtable already exists), every core→TLS coupling site classified (no direct OpenSSL calls outside the backend; the one `->bundle` reach-through), real OpenSSL/LibreSSL/BoringSSL API drift found in-tree, variant-A multi-backend vtable effort (~2–3 w, wasm-ops precedent, HAProxy/curl precedents), and a kTLS plan (data path at `c->io` swap, sendfile forced OFF under TLS today, `SOL_TLS` per-connection install, SCM_RIGHTS risks); verdict = two tracks, A first

### Protocol & Architecture
- [router-threads-and-blocking-io](engineering/router-threads-and-blocking-io) — the router is multi-threaded since 1.33 (`settings.listen_threads`, default ncpu, one shared listening fd, no `SO_REUSEPORT`); parsing cannot wedge an engine, but the request-body spill writes synchronously (`nxt_fd_write`) on the router thread; slow-client state: headers one-shot budget (safe), `body_read_timeout` a gap timer with no rate floor (PR #508), no connection cap; `/status` sums per-engine counters
- [bwp-protocol-specification](engineering/bwp-protocol-specification) — BWP (Buran Worker Protocol) v1 specification
- [buran-shared-memory-prototype-fork](engineering/buran-shared-memory-prototype-fork) — Shared opcache/APCu via prototype+fork
- [connection-flow-visualization](engineering/connection-flow-visualization) — Full HTTP request flow: accept → parse → route → IPC → worker → response
- [http2-in-freeunit](engineering/http2-in-freeunit) — HTTP/2 in the C core: PRs #458/#459 (phase 0), #463 (stage 1, nghttp2 over TLS/ALPN), #467 (stage 2); cost vs the KB estimate, the nghttp2 build-dependency decision, D3 tension, gaps; sequenced **last** in the wave
- [pr-wave-438-469-merge-plan](engineering/pr-wave-438-469-merge-plan) — ordered merge plan for the #443 wave (#438–#469): phases, stacked dependencies, the open UAF/lifetime cluster (#414/#415/#425/#455/#464/#465), and the decisions to settle before merging
- [opencode-free-tracking](engineering/opencode-free-tracking) — OpenCode Free tier: keyless access, per-model limits, profile accumulator, zen-quorum
- [zen-quorum-wasm-stop-the-rest-of-the-request-path](engineering/zen-quorum-wasm-stop-the-rest-of-the-request-path) — quorum on PR #320 (wasm abort follow-up): blind-run artifact vs fixed run, SPOT ground truth, APPROVE with non-blocking notes
- [evolver-reference](engineering/evolver-reference) — tree-sitter→symbols→SQLite pattern for cross-version code analysis (vs vector); replicate for unit/Mimic
- [diff-symbols-poc](engineering/diff-symbols-poc) — understand code logic via PR diffs (diff_symbols table, watermark fill, rename tracking); POC on unit commit 73cc8cc8
- [gh-archive-tool](engineering/gh-archive-tool) — tools/gh_archive.py: one-shot bulk dump of a repo's issues/PRs/comments into JSONL + FTS5 sqlite for zero-API offline search; nginx/unit archived (1554 items, 2017→2025) fully dumped
- [unit-archive-acme-cron-survey](engineering/unit-archive-acme-cron-survey) — six-theme sweep of the full unit archive (ACME #424, PUT-overwrite #195, mTLS #225/#547, scheduler #1528 rejected, peer-cred ancestor #307, ECDSA #358); X10 is upstream-rejected, not catch-up
- [ops-environment-facts](engineering/ops-environment-facts) — yt-dlp Hetzner block, uv quirks, Telegram no-tables, cron script rule, glab aports
- [inbound-cn-domain-scam](engineering/inbound-cn-domain-scam) — template "CN registrar" email (freeunit .cn pitch, "Zhenyi Holdings"/"Frank Lee"): scam signature, whois facts (freeunit.cn held since 2017 to 2031; .com.cn/.net.cn/.org.cn free), no-reply policy
- [acme-tls-plan](engineering/acme-tls-plan) — ACME/auto-TLS ladder (PUT-overwrite → sidecar → in-daemon); needs a TLS **client** (shares X11); priority over Control-API auth for release readiness
- [acme-certbot-thin-layer](engineering/acme-certbot-thin-layer) — "прослойка": certbot does all ACME; Unit needs only an HTTP-01 route + a deploy-hook that PUTs the bundle to Control API. Both tested live. HTTP-01 works today (no X11); TLS-ALPN-01 still needs X11.
- [acme-step3-indame-language](engineering/acme-step3-indame-language) — Step 3 (in-daemon shim) language check: Rust vs Go. http-01/tls-alpn-01 need no DNS providers → Rust/C in-daemon; the 200-provider engine is Go/lego and belongs in the sidecar (Step 2), not unitd. Don't embed the Go runtime in the daemon.
- [readiness-capget-rootfs](engineering/readiness-capget-rootfs) — readiness for capget #254 (ready-unmerged, capset-drop follow-up) + rootfs chain #279/#274/#273
- [zen-review-pr-276](engineering/zen-review-pr-276) — router listen-socket close/ack ordering; two-phase ack (verified merge)
- [zen-review-pr-285](engineering/zen-review-pr-285) — static-serving truncation guard (n==0) re-add; narrowed, APPROVE (ac000/F5)
- [zen-review-pr-294](engineering/zen-review-pr-294) — pkg(eol) Ubuntu/Debian EOL sync + Debian LTS field mapping; data/docs, APPROVE
- [zen-review-pr-265](engineering/zen-review-pr-265) — PHP automount.language_deps mounts (tzdb rootfs SIGSEGV); MERGED; tz-probe fallback to /usr/share/zoneinfo, "-\-refusal (JSON %s serializer), quorum→tool-verified
- [zen-review-pr-254](engineering/zen-review-pr-254) — capget keep-running when filtered + drop capabilities (ERRNO-narrow, NXT_DECLINED split, merlist still_held); MERGED, security P0
- [zen-review-pr-298](engineering/zen-review-pr-298) — review follow-ups to bodyless upstream: &r->task ptr, static is_bodyless, port-registry row; mechanical APPROVE
- [zen-review-pr-299](engineering/zen-review-pr-299) — listener-close-before-ack regression test for #276; anchored on close(2), MERGED (+P2 resolved: test_configuration in --debug sanitize leg)
- [zen-review-pr-301](engineering/zen-review-pr-301) — discovery escape module list as JSON via nxt_conf (%s-serializer broke parse); +parse-fail alerts (main_process), MERGED
- [zen-review-pr-290](engineering/zen-review-pr-290) — main state-store atomic (tmp→fsync→rename→dir-sync, fail deletes tmp); fixes data-loss #215, MERGED (test: 64KiB tmpfs)
- [zen-review-pr-291](engineering/zen-review-pr-291) — refuse MSG_CTRUNC (SCM_RIGHTS cut) cross-language; APPROVE + P1-risk follow-up (trunc-path diverges from recheck-handoff nxt_port_socket.c:959)
- [zen-review-pr-304](engineering/zen-review-pr-304) — keep access-log values inside UTF-8 (nxt_utf8_sanitize at log sink, NOT escaper — zero config blast radius) + refuse surrogates in utf8_decode2; MERGED, per-byte (not max-subpart), escaper untouched
- [zen-review-pr-302](engineering/zen-review-pr-302) — runtime pid-file short-write resume (offset=written, alert on n==0); follow-up to #290, MERGED
- [zen-review-pr-303](engineering/zen-review-pr-303) — string: NULL + zero-length mem* guards (nxt_cpymem/nxt_strstr_eq/nxt_is_tstr); closes #200-code, MERGED
- [zen-review-pr-307](engineering/zen-review-pr-307) — harness fix: wait for workers gone before deleting temp_dir (java late-start alert); read log tail after teardown so alert ≠ next test; MERGED
- [zen-review-pr-284](engineering/zen-review-pr-284) — access log object-format per-member (log-injection); depends on #304 for full guarantee, MERGED
- [zen-review-pr-280](engineering/zen-review-pr-280) — optional limits.start_timeout on app start; timer-vs-reply via payload-completion, idempotent armed/expired; MERGED
- [utf8-encoding-contracts](engineering/utf8-encoding-contracts) — P0-P7 plan: three encoding contracts (opaque/UTF8-reject/UTF8-substitute); #304 should be reworked→P2 sanitizer at log sink, not escaper; B0 wasm abort
- [php-phar-history-vulns](engineering/php-phar-history-vulns) — php-src phar 5yr: security-class (symlink-cycle/UAF/leak), `phar_get_link_source` two-generation patches (Floyd vs depth), `zend_string*` refactor removes UAF-class, behavioral `.phar`-only auto-detect
- [zen-review-pr-289](engineering/zen-review-pr-289) — authenticate prototype's START_PROCESS (sender-pid, 2 arms: global-pid / ns-0) + retire start stream on reply; security MERGED (fixes #270/#271)
- [zen-review-pr-282](engineering/zen-review-pr-282) — compression shm leak (nxt_buf_free skipped completion_handler); chain walk, MERGED
- [zen-review-pr-288](engineering/zen-review-pr-288) — prototype-death stranding START_PROCESS RPC (no peer); _ex_set_peer one-line fix, APPROVE
- [zen-review-pr-295](engineering/zen-review-pr-295) — proxy bodyless upstream (HEAD/204/304 completed on headers); is_bodyless_final split, MERGED; +buf_mem_hold (pool cleanup releases retain, keeps fields valid)
- [zen-review-pr-296](engineering/zen-review-pr-296) — prototype-kill test skip-outside-window guard + pid#tid regex fix; test-robustness, MERGED
- [zen-review-pr-279](engineering/zen-review-pr-279) — isolation reject rootfs+credential-ns w/o mount-ns (config-time kernel invariant); MERGED; validator declares-not-stats (euid-distinct), names the automount knob
- [zen-review-architecture](engineering/zen-review-architecture) — zen_review.py + gh_cache.py: entity-sliced review (issue/pr/commit), script vs agent, local GitHub/GitLab cache with watermark delta
- [opencode-free-tracking](engineering/opencode-free-tracking) — keyless OpenCode Free tier ground truth; **2026-10-03: tier now client-gated (403 "can only be used from within OpenCode") — only space-bunny-free still answers keyless**
- [refusal-aware-model-bench](engineering/refusal-aware-model-bench) — refusal/fallback taxonomy (REFUSAL vs EMPTY-LENGTH budget artifact vs ANALYSIS-NO-PATCH) + framing ladder (review→exploit→patch) for security-adjacent code tasks; vendor KCB 2.0 disclosure vs what we can measure; live finding: the one empty answer was budget exhaustion, not a refusal

### PHP & Drupal
- [octane-roadrunner-frankenphp-research](engineering/octane-roadrunner-frankenphp-research) — Persistent-worker landscape: Octane, RoadRunner, FrankenPHP
- [roadrunner-v3-jobs-vs-freeunit-schedules](engineering/roadrunner-v3-jobs-vs-freeunit-schedules) — RoadRunner v3.0.0 `jobs` (broker-fed **queue**) vs FreeUnit `schedules` (#452, in-process **timer**): different axes; RR v3 ships **no scheduler**; overlap is only named worker pools + outcome metrics/tracing
- [drupal12-symfony-runtime-persistent-workers](engineering/drupal12-symfony-runtime-persistent-workers) — Drupal 12 + Symfony Runtime for persistent workers
- [drupalcon-bof-plan](engineering/drupalcon-bof-plan) — DrupalCon BoF plan (Sep 2026) — **aspirational: non-existent CLI/YAML/worktree demos; do not quote**; grounded replacement: [strategy/drupalcon-rotterdam-2026-promotion-plan](strategy/drupalcon-rotterdam-2026-promotion-plan)


### Security
- [port-message-trust-model](engineering/port-message-trust-model) — #341 classified: no sender ACL in the router's dispatcher, what IS gated (main/prototype/cert/script/socket/access-log), `.restart = 1` caps a forged QUIT at one teardown, and the wording to use in public
- [port-frag-eviction-and-convergence](engineering/port-frag-eviction-and-convergence) — #447's 64-stream cap is bypassable (no **time** bound → hold slots forever); fix = timeout eviction (+ optional evict-oldest) and/or refuse fragments from untrusted senders; falsifiable exit criteria (count+bytes+**time** bound, read-once, sender auth) for the "untrusted SHM" class
- [buran-vs-freeunit-frag-hardening](engineering/buran-vs-freeunit-frag-hardening) — how Buran avoids the class by construction (no peer-writable SHM: atomic SOCK_DGRAM + framed stream); where it reassembles (WebSocket) it bounds by `max_message_size` + `idle_timeout` and never trusts a declared length; the bounds map 1:1 onto #446/#447/#448/#505, and Buran adds the two **time** bounds FreeUnit still lacks (idle timeout, `min_rate`)
- [test-port-strategy-freeunit-vs-buran](engineering/test-port-strategy-freeunit-vs-buran) — why FreeUnit's suite needs a port-remap layer (#406) for parallel runs, and how Buran sidesteps it by binding `127.0.0.1:0`
- [seccomp-isolation-plan-summary](engineering/seccomp-isolation-plan-summary) — Seccomp / Docker profile / isolation collission analysis
- [release-1.36.0-what-we-fixed](engineering/release-1.36.0-what-we-fixed) — Full accounting of 38+ fixes in 1.36.0 by category
- [release-1.36.2-pending-includes](engineering/release-1.36.2-pending-includes) — triage of the #500+ wave for the pending 1.36.2: security/DoS patch-worthy (#508 min-rate, #515 cgroup-ns, #517 wasm OOB, #520 ReDoS, #521 rootfs symlink escape, #522 WS ping flood), bugfix (#518 leak, #519 rpc-stream-0), feature (#523/#516 async state store)
- [audit-priority-matrix](engineering/audit-priority-matrix) — Security audit priority matrix (14 vectors)
- [control-api-auth-d7](engineering/control-api-auth-d7) — Control API auth (D7/A1, R1 w9.5): unix peer-cred gate exists (1.36.0); TCP bypass + no bearer/mTLS; upstream nginx/unit #1315/#840/#1000/#225 arguments. **TO DISCUSS WITH TEAM**
- [syscall-audit-kernel-requirements](engineering/syscall-audit-kernel-requirements) — Kernel syscall requirements for the io_uring engine
- [capget-fallback-plan](engineering/capget-fallback-plan) — capget(2) filtered → warn+continue (A4/P0, supersedes old "P0 capget-prod" assertion)
- [port-ready-provenance](engineering/port-ready-provenance) — PROCESS_READY sender/auth via SCM_CREDENTIALS (PR1 of #231)

### Telemetry & Observability
- [telemetry-status-reference](engineering/telemetry-status-reference) — /status, OTel, access logs, cgroup stats — read & configure
- [otel-perf-regression-221](engineering/otel-perf-regression-221) — OTel CPU regression #221: fix 1-6 merged, fix 7 consciously deferred

### Scheduled Tasks (cron-like)
- [scheduled-tasks-plan](engineering/scheduled-tasks-plan) — Daemon-internal scheduler: ACME renew, module swap, config re-apply (built-in actions only); pairs with X11 modular TLS; §X10 upstream-rejection (#1528) + IPC-emulation counter-argument
- [scheduled-tasks-app](engineering/scheduled-tasks-app) — App-level scheduler (drush/cron, Celery, Sidekiq): control `/run` primitive, `schedules` config, Phase 1-3 path
- [x10-job-shim-spike](engineering/x10-job-shim-spike) — spike: run supervised long-lived jobs in Unit via ASGI lifespan (Python, executed ✓) or a C libunit shim; reuse for ACME (one app = scheduler + ACME client + deployer) → needs idle_timeout:0 + spare>0
- [artisan-worker-stubs](engineering/artisan-worker-stubs) — per-artisan Unit worker stubs (queue:work/schedule:work/horizon): Python ASGI supervisor (PHP has no boot hook — TrueAsync not compiled) + gen_stubs.py; tested live (restarts observed)
- [drupal-cron-queue-stub](engineering/drupal-cron-queue-stub) — Drupal cron/queue via a **scheduler** stub (drush one-shot ticks, not a supervisor); `core:cron` + per-queue `queue:run` tickers; tested live; uses app-level schedulers so no host cron
- [wordpress-cron-queue-stub](engineering/wordpress-cron-queue-stub) — WordPress wp-cron (pseudo-scheduler → `wp cron event run --due-now`) + Action Scheduler (`wp action-scheduler run`) as one Unit app; two awaited tickers; tested live
- [opcache-inprocess-fork](engineering/opcache-inprocess-fork) — Unit PHP workers SHARE opcache via prototype+fork (proven: reset in one clears the other); enable via `options.file` php.ini (zend_extension=opcache, separate php84-opcache pkg). Stub children are separate CLI procs → use `opcache.file_cache`. In-process jobs blocked by no PHP boot hook (TrueAsync)
- [fork-spawn-php](engineering/fork-spawn-php) — the "спан": `pcntl_fork` in a request handler → child inherits warm opcache + returns HTTP in ~4ms; double-fork+setsid → no zombie. **Gotcha: `exit()` in a Unit fork child does NOT terminate it (leaks a worker per tick) — die by SIGKILL + reap.** Long Drupal/WP/artisan jobs with NO TrueAsync; use for tests + blue/green
- [fork-spawn-drupal-measurement](engineering/fork-spawn-drupal-measurement) — measured twice over: real `DrupalKernel`+`cron` in the fork child — warm tick **0.049s** vs **0.42s** cold CLI (kernel ≈10×, cron ≈7.5×; cached_scripts frozen at 593, hits 1→1780 → SHM shared); stub tick via fork-spawn endpoint **0.004s** vs **0.70s** with real Drush 13.8.0 (≈175×, the 0.52s shim was a lower bound); `queue:run` of 50 real items: warm child 0.18s vs cold CLI 0.26–0.31s vs Drush 0.68s — the work itself is unchanged, only the per-tick start-up disappears; per-tick memory: warm child 11MB RSS vs 36/57MB cold CLI/Drush; first tick always pays the opcache fill (~0.41s)
- [freeunit-1361-rootless-live-test](engineering/freeunit-1361-rootless-live-test) — ran published freeunit 1.36.1 rootless on Alpine: WSGI+ASGI+PHP(8.4.25)+X10 job-shim all serving live; PHP RUNPATH=/usr/lib/php84 patched via patchelf; spare/idle_timeout nested under processes

### Rust toolchain
- [rust-toolchain-policy](engineering/rust-toolchain-policy) — Rust MSRV (1.88), release cycle (no-LTS, 6-week), watch 1.100 (edition 2024), NOT in eol.json

- [dependency-ci-hygiene](engineering/dependency-ci-hygiene) — Verified 2026-09-16 inventory, CI state re-verified 2026-10-09 (master 0f1ec0b1): how dependencies are pinned (pkg/contrib versions + SHA512SUMS, pkg/eol.json as EOL/audit truth), every CI gate on master (audit/clang-ast/sanitize/fuzzing/seccomp/syscalls/whitespace/eol-check/rust-version/macos), and what is still open (#632 no 32-bit compile job, #624 s390x hang, #308 wedged checkout leg, #402 Python leg sleeping tests, PRs #449/#450 gates, #617/#626 drafts, dependabot gomod+docker, no style gate); closed since: #400 wasmtime pin, PR #99 Trivy (no), OpenSSL ceiling 3.5.9/4.0.3, cargo dependabot

### Docs & Roadmap
- [todo-md-audit](engineering/todo-md-audit) — TODO.md staleness audit (2026-09-16, master df9843b0): plans 1.35.6/7/8 that never existed, OTel remaining-work block already done at HEAD, TrueAsync branch framing dead, OpenSSL 3.6 checklist done, chunked/#58 sections shipped in 1.35.5; section-by-section action table

### Code volume & release delta
- [tls-module-prototype](engineering/tls-module-prototype) — W1 verified prototype (2026-10-11, PR 23 in freeunit-exp): the interface a loadable TLS module exposes, an OpenSSL backend, a smoke test that passes three ALPN cases on a clean runner (no ALPN → HTTP/1, http/1.1, h2); records the trap (the select callback must set *out to the protocol NAME, not the length-prefixed entry, or every client answers decode error) and the diagnosis method (run the no-ALPN case first); open: TLS 1.3 NOACK semantics, cert-reload ownership, health, load model
- [h3-research](engineering/h3-research) — W3 research + spike (2026-10-11, PR 24 in freeunit-exp): userspace QUIC/H3 on loopback measures 32.8/2.7 ms here and 35.4/0.8 ms in CI (shape, not a C number); the three options (in-house QUIC, library ngtcp2+nghttp3, edge proxy) with cost drivers; prerequisites in order (TLS 1.3 + the ALPN token `h3` in the module = the only hard W1 coupling, then h2 shipped, then D3 body streaming, then a UDP event path); recommendation: library over in-house, no start before h2 + D3; do-not-claim list
- [webhook-reaction-quantization](engineering/webhook-reaction-quantization) — design note 2026-10-11 (subagent, verified): Hermes already ships the coalescer (`gateway/platforms/webhook_coalesce.py`, route key `coalesce`, `window_seconds` 30, `max_wait_seconds` 300) → quantization is a config addition, not new code; key `{{repository.full_name}}#{{number}}`, newest arrival supersedes, bypass for direct address and for `issues.opened`, record in `cron/webhook-reactions.jsonl`; baseline in the note: 21 deliveries / ~0.7 turns per hour, 538 filtered, **21 % of runs end with the iteration budget exhausted and post nothing**
- [oracle-cloud-arm-stand](engineering/oracle-cloud-arm-stand) — plan 2026-10-11: armv7 probe first (AArch32 on Ampere A1 is unverified — five-minute test before any build), then native aarch64 build/test metrics (three runs, spread reported), then install metrics (cron runs/duration/delivery, webhook classes, turns per quantum); counts and timings only, no payloads; needs SSH, shape, OS from the owner
- [research-backlog](engineering/research-backlog) — 2026-10-11: ten clusters worth investigating with no hardware (CI cost, libunit↔router IPC lifecycle, CVE map, ACME, timeout/buffering semantics, static contract, module health, 32-bit class, worker-mode readiness, K8s posture), each ending in one KB note with evidence and a do-not-claim list
- [tls-1.3-and-kubernetes](engineering/tls-1.3-and-kubernetes) — deep research 2026-10-11, priority 1.38: TLS 1.3 already works but **only via `conf_commands`** (docs' own example: `minprotocol: TLSv1.3` + `ciphersuites`), no version/cipher member, SNI works through arrays of bundles, mTLS **code path exists but no config surface** (`ca_certificate` → `SSL_VERIFY_PEER`, depth pinned 1, two TODOs), rotation via `PUT /certificates/<name>`; 1.38 scope P0 (protocol/cipher members, client CA member + verify callback), P1 (module carries 1.3 and the `h3` token, rotation contract + test), P2 (refuse 0-RTT); deferred: OCSP, ECH, PQC, per-SNI policy; verify: OpenSSL floor gates `conf_commands`, rotation atomicity; prior art: no upstream TLS 1.3 or SNI demand thread
- [code-volume-and-release-delta](engineering/code-volume-and-release-delta) — measured 2026-10-05: runtime C 65 614→70 682 (+7.7%) while tree 107 805→142 666 (+32%); tests 17.1%→31.5% of code (tests:runtime 0.28→0.64); 1.37.0 = 314 commits / 211 PR / 68 issues closed / churn +76 250−12 522 (56% tests, 126% of the runtime C base); era 679 commits / 377 PR / 86 issues / net +98 029 = 139% of runtime C; method, validation and caveats inside
- [release-1.37.1-forecast](engineering/release-1.37.1-forecast) — checked 2026-10-09: 1.37.1 cycle = 71 commits / 52 PR / +8 352−1 268 (tests 47.8% of insertions), CHANGES 15 entries (14 Bugfix, 1 Change, 0 Security/Feature), version still 1.37.0; rate ~14.9 commits/day (≈6× the 1.36.1 cycle) → release window 12–18 Oct 2026 at 95–140 commits / 65–95 PR; 1.38.0 staging ≈ +35 200 insertions (h2 stack, schedules, USDT, status socket, PCRE2 JIT); blockers: audit issues #537/#538/#539 open with no Security entry yet, #632 32-bit gate missing, #624 s390x hang


- [cgroup-v2-isolation-performance-brief](engineering/cgroup-v2-isolation-performance-brief) — isolation research brief (2026-10-11, **HOLD until the 1.37.1 tag**, filed as `freeunit-exp#22`): verified state (`isolation.cgroup` = `path` only, Unit places and never writes limit files; CPU-limit walk lowers `nxt_ncpu` once at startup; #548/#547/#576/#515 merged, #659 open), 6 questions (v2 delegation, no-internal-processes, threaded subtrees, rootless, v1/hybrid, operator recipes), performance measurement set (ncpu effect, throttling trace, restart-only semantics, memory.max vs shared opcache, per-app OOM, quota vs `processes.max`), deliverables and out-of-scope


- [1.36.0 release (EN)](releases/1.36.0-announcement-en) — Fact-checked release announcement (English)
- [1.36.0 release (RU)](releases/1.36.0-announcement-ru) — Fact-checked release announcement (Russian)
- 1.36.1 release (2026-08-29) — LIVE: Docker (75 jobs), deb, unitctl. See [v1/release-1361](v1/release-1361)
- [1.37.0 in-flight classification](releases/1.37.0-in-flight-classification) — MINOR per policy: 2 features (byte-range, conditional requests), unitctl YAML/JSON5/TLS breaking changes, 6 Security entries; CHANGES header still says 1.36.2 and 4 static issues stay open → fix before tagging *(historical: the tag `1.37.0` was cut 2026-10-04 with a 116-entry section)*
- [Release 1.37.0 — description check](engineering/release-1.37.0-description-check) — reproduced: the release body's install commands 404 (`~` vs the `.` GitHub stores), `SHA256SUMS` names never match a download, body carries packaging text instead of notes; CHANGES↔changes.xml one entry apart; no GHSA for the 16 Security entries; version/tag/date and the change coverage are correct


- [operating-principles](engineering/operating-principles) — Memory vs KB separation rule (Andrey)
- [okf-kb-handover](engineering/okf-kb-handover) — Briefing to hand the OKF KB to another Hermes agent: layout, conventions, read/write workflows, measured integrity (142 docs / 679 edges; 11 dangling index links, 35 unindexed files → index is an entry point, not a manifest), tiered file handover list (A bootstrap / B project context / C topical / D tooling)
