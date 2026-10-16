---
title: "freeunit-exp experimental tracks — harness lanes and workbench state"
description: "The bot workbench freeunitorg/freeunit-exp: live PRs, branches and issues, the four topics a status question names (TrueAsync, QuickJS, v2, syscall audit) with what is PoC, what shipped upstream and what was removed, and the harness lanes (who runs which model)"
format: "open-knowledge-format-v1"
updated: "2026-10-13"
maintainer: "andypost"
---

# freeunit-exp — workbench state and experimental tracks

_Read 2026-10-13 from live `gh api` (REST) and a local clone of
`freeunitorg/freeunit-exp` (`git fetch --prune` first). Every number below is
MEASURED on that date unless marked otherwise. Method: `gh api
repos/freeunitorg/freeunit-exp/{branches,issues,pulls}?per_page=100`, then
`git rev-list --count origin/master..origin/<branch>` for the ahead/behind
figures. Two caveats: `/issues` includes pull requests, so the two lists overlap
(PR numbers are not issue numbers); the ahead/behind counts move with every
merge, so re-derive them before quoting._

## 1. What the fork is

A fork of `freeunitorg/freeunit` used as an **unattended-agent workbench**. Rules
in `HERMES.md`: never push upstream; the tracking branch mirrors upstream; branch
names carry the task; fork CI is context for a review, never a substitute for
upstream CI. Write identity is the GitHub App `app/freeunit-agent[bot]`,
installed on this fork and the research repo only. Merging stays human.
Output layer: top-level `findings/` (agent findings, `verified` marker),
`reviews/` (PR review notes, added by PR #5), `digests/`.

## 2. Live state (2026-10-13)

- Default branch `main`; `main` = upstream `2dc6596f` (synced by PR #38,
  merged 13.10) + 19 fork commits. Upstream has moved on to `678ef06d`, so
  `main` is one sync behind. Fork `master` = `4fef769d` (12.10) and is an
  **ancestor of `main`** — the sync now lands on `main`, not `master`
  (open issue #26 asks for this to fail loudly).
- **10 open PRs**, **8 open issues**.
- Bot lane (`hermes/*`, commits authored as `freeunit-agent[bot]`): 9 branches.
- Maintainer lanes: `ktls-prototype`, `claude/fix-upstream-sync`,
  `python/base-prefix-home`.

### Open PRs

| PR | Branch | Ahead/behind vs fork master | Subject |
|---|---|---|---|
| 5 | `hermes/review-645` | 3 / 12 | review note: libunit SHM_ACK wait shrink |
| 21 | `hermes/stream-map` | 7 / 12 | docs: stream map with discussion index |
| 23 | `hermes/tls-module-proto` | 10 / 12 | exp(tls): loadable TLS backend module (W1) |
| 24 | `hermes/h3-research` | 5 / 12 | exp(h3): transport spike + verdict note (W3) |
| 25 | `hermes/libunit-wakeup-nonblock` | 2 / 0 | libunit: no block on wake-up in context free (issue 663) |
| 26 | `claude/fix-upstream-sync` | 5 / 12 | ci: upstream sync fails loudly, mirrors master |
| 28 | `hermes/tls-table-conn-init` | 6 / 12 | exp(tls): connection entry through the backend table |
| 30 | `hermes/ktls-probe` | 24 / 12 | exp(ktls): probe the kernel offload path in CI |
| 31 | `ktls-prototype` | 5 / 12 | tls: opt-in kernel TLS for listeners, prototype |
| 33 | `hermes/h1p-conn-null-crash` | 5 / 12 | h1p: 1.37.0 `segfault at 0x50` fix + test |

### Open issues

| Issue | Author | Subject | State |
|---|---|---|---|
| 6 | andypost | verify T1/T2 findings against Unit + Drupal source | answered by merged PRs #7/#8; wants closing |
| 11 | bot | rework list from the 1.37.1 review archive (74 PRs) | open; section A blocking items |
| 22 | bot | isolation + cgroup v2 brief | open, **HOLD until the 1.37.1 tag** |
| 27 | bot | `ci`: layout check cannot run on a branch-creating push (all-zero `before` sha) | open |
| 29 | bot | kTLS step 1: probe the kernel offload path in CI | open |
| 32 | andypost | static: file handler copies through memory buffers, not `sendfile` | open |
| 34 | andypost | kTLS step 2: `SSL_sendfile()` for file buffers, nginx parity | open |
| 36 | bot | agent task: add a 32-bit musl leg (Alpine i386) to `build-test.yml` | open |

Closed trail: #1 daily upstream fast-forward, #2/#3/#4/#10 webhook tests,
#7/#8 findings (merged), #9 README marks the fork experimental, #35 TLS alert
reason 209, #37/#38 upstream syncs (merged 13.10). Findings that landed:
`findings/T1-php-option-type.md` (the PHP option value is string-only, by
design) and `findings/T2-drupal-drush-install.md` (Drupal core install owns
SQLite; `hash_salt` gates the form).

Watch: cron `beda723c07c7` (`20 */2 * * *`, no_agent) runs `fu-exp-watch.py` and
delivers new/updated issues and PRs of the fork. `freeunit-exp` is deliberately
**not** in the watermark change tracker (its `main` replays upstream).

## 3. The four tracks the question asks about

### 3.1 TrueAsync — REMOVED upstream, not an active track

- **Not in this fork.** No `trueasync` branch, PR or issue exists here.
- **It was removed from the server in 1.37.0**: commit `b20aeb78` ("php: remove
  the TrueAsync code path", changelog `118b28f3`), inside tag `1.37.0`. The
  `CHANGES` 1.37.0 entry records why: the code targeted a `zend_async_event_t`
  API expected in PHP 8.5 core, which did not ship; the configure probe never
  succeeded; the code sat behind `#if NXT_PHP_TRUEASYNC` in every build and could
  not have compiled (it read `async`/`entrypoint` members that
  `nxt_php_app_conf_t` has not got and called an undefined
  `nxt_php_extension_init()`). The probe, the `entrypoint` target key and the
  TrueAsync test suite went with it.
- Earlier history: 1.35.2 shipped a graceful-shutdown fix "for PHP workers in
  TrueAsync mode" — that section is now the project's only TrueAsync trace in
  the tree besides the removal note.
- **KB correction.** An older `repos.md` line listed `freeunitorg/trueasync-experiment`
  ("TrueAsync experiments (v3)"). `gh api repos/freeunitorg/trueasync-experiment`
  and a GitHub name search both return **404 / no result** on 2026-10-13, and the
  org repo list does not contain it. Treat that line as stale. The real external
  project is the **`true-async`** org (`true-async/php-async`, a PHP core
  extension implementing the TrueAsync ABI); the FreeUnit repo has no dependency
  on it and no code path for it.
- Older KB lines that say "TrueAsync not compiled" (artisan-worker-stubs,
  opcache-inprocess-fork, fork-spawn-php, index docs/roadmap note) described the
  pre-1.37.0 state. Correct reading today: the path is **gone**, so "rebuild the
  module to get in-process jobs" is no longer a candidate route.

### 3.2 QuickJS — not a FreeUnit experiment; one build flag only

- Only touchpoint in the whole tree: `pkg/contrib/src/njs/Makefile` configures
  njs with `--no-quickjs`. The comment states that njs 1.0.1 recommends QuickJS,
  but that needs an external QuickJS / QuickJS-NG library, so the build keeps the
  baseline deterministic. **No FreeUnit QuickJS runtime, module or PoC exists.**
- The only other QuickJS trace in our material is packaging, not product:
  Alpine aports `main/quickjs-ng` (andypost MR !105133, upgrade to 0.15.1).

### 3.3 FreeUnit v2 (PoC)

- **FreeUnit v2 (PoC)** — a separate track, Rust orchestrator + NTS PHP workers
  on Revolt, hypothesis = hang detection by TGID polling + PING/PONG with no FFI
  and no PHP runtime change. **PoC complete 2026-06-15, development stopped**:
  38/38 issues closed, 76 tests green, H1–H6 proven on PHP 8.5.7 NTS. Three
  related repos: `freeunit2`, `freeunit2-fnb` (`Request.id` multiplex),
  `freeunit2-a4v` ("fair three-way" vs RoadRunner and FrankenPHP). Nothing from
  v2 is in the server tree; the frontend role it aimed at is now held by the
  TLS/H3 module track on FreeUnit itself.

### 3.4 Syscall audit

- Research: `syscall-audit-kernel-requirements.md` (2026-07-16, branch
  `pre-1.35.6`): direct syscalls, glibc wrappers, namespace flags and the Docker
  seccomp interaction, plus seven recommendations.
- **The CI job exists and is advisory**: `.github/workflows/security-syscalls.yml`
  — "Security (Syscall Drift)", `continue-on-error: true`, matrix `glibc`/`musl`,
  runs pinned containers (`debian:trixie-slim`/`alpine:3.22`), captures the
  syscall set with `test/syscalls/run-in-docker.sh`, uploads it as an artifact
  even on failure, then diffs it against the committed baselines
  `test/syscalls/baseline-linux-{glibc,musl}.txt`. `test/syscalls/README.md`
  holds the four-step sequence (one commit) that makes the gate blocking.
- The Docker/seccomp side has its own gate: `security-seccomp.yml` (AF_ALG
  profile, hardening matrix, `src/nxt_capability.*`, `nxt_credential`,
  `nxt_isolation`).
- The KB document's recommendation to make the syscall job blocking is therefore
  **partly done** (job shipped, advisory) and partly **open** (no committed
  baseline from CI yet).
- Recommendation 3 of that document (make `capget` failure non-fatal) is **done
  and shipped in 1.37.0** (PR #254).

## 4. Harness lanes (who runs which model)

The two corrections this note
adds:

1. The workbench's own lane is recorded only by trailers. In
   `origin/master..origin/hermes/*`: `Reviewed-by: FreeUnitOPS (DeepSeek V4.1
   Flash, Hermes Agent)` ×3 and `Co-Authored-By: pi muse-spark-1.3` ×1 — so the
   bot lane is DeepSeek V4.1 Flash under Hermes Agent, with one free-model
   contribution. Per-PR attribution is usually not recorded (App identity).
2. The maintainer's own pipeline is Claude-heavy for authoring/review, with
   DeepSeek V4.1 Flash as the cheap independent pass and the Codex app as the
   third opinion. The FreeUnit server tree's own trailer counts agree with that
   split.

## See also

- `engineering/freeunit-satellite-repos-2026-10.md` — the four output repos
- `engineering/freeunit-harness-public-toolkit.md` — the published toolkit
- `engineering/tls-module-prototype.md`, `engineering/h3-research.md` — the W1/W3 notes behind PRs 23/24
- `engineering/syscall-audit-kernel-requirements.md` — the audit and its recommendations
