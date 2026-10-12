# FreeUnit 1.37.1 — cycle state and release forecast (checked 2026-10-09)

## State at check time

- master HEAD `0f1ec0b1` (2026-10-09 00:04 +0200) — "libunit: keep websocket frames in
  order across a wait for a segment" (PR #573).
- Since the 1.37.0 tag (2026-10-04 17:55 UTC): **71 commits**, **52 merged PRs**
  (#562–#636), net **+8 352 / −1 268 over 152 files**.
- Churn split of the cycle: runtime C +2 443/−620 (33 files) · unit tests C +1 756/−65
  (15) · integration tests Python +2 236/−72 (31) · unitctl +214/−156 (6) ·
  docs/CI/meta +1 703/−355 (67). **Tests are 47.8% of insertions.**
- `CHANGES` 1.37.1 section: **15 entries — 14 Bugfix, 1 Change, 0 Security, 0 Feature**.
  The one Change is "--otel no longer needs OpenSSL" (PR #575); the bugfixes include the
  websocket frame-order fix, the control-API listener without pass/application, macOS
  16 KiB pages, chunked_transform 400, state-dir `version` file with a trailing newline,
  wasm export/import crashes, `large_header_buffers` 8-bit counter, 64-bit `shm` cut to
  32 bits, PHP stale cwd, unbounded timeouts in the control API, 32-bit gcc build,
  refused WHOAMI forever-wait.
- `version` file is still `1.37.0` (NXT_VERNUM=13700): the release commit has not been
  made, so the cycle is open.
- Open queue: **35 PRs** (14 labelled feature, 20 unlabelled, 1 bugfix, **0 security**) and
  **53 issues** (44 unlabelled, 7 bugfix, 1 feature, 1 infra).

## Cadence measured

| Cycle | days | commits | PR merged | insertions | commits/day |
|---|---|---|---|---|---|
| 1.36.0 | 48 | 139 | 56 | 19 034 | 2.9 |
| 1.36.1 | 42 | 99 | 69 | 12 993 | 2.4 |
| 1.37.0 | 36 | 314 | 211 | 76 250 | 8.7 |
| **1.37.1 so far (4.8 d)** | 4.8 | 71 | 52 | 8 352 | **14.9** |

The current patch cycle runs at roughly 6× the 1.36.1 rate: ~10.9 PR/day and
~1 750 inserted lines/day. CHANGES entries accumulate at ~0.29 per merged PR
(15 entries / 52 PRs).

## Forecast (hypotheses, not commitments)

- **Content**: 1.37.1 ships as a bugfix patch — no Feature and no API/breaking Change is
  in the section today, and the wasm/websocket/chunked fixes are the kind that a patch
  carries. Hypothesis: 20–30 CHANGES entries at the release commit, dominated by Bugfix,
  with 0–3 Security entries depending on whether the open 2026-10-03 audit items land.
- **Volume at release**, if the cycle closes inside the next 3–10 days (from the measured
  rate, no plateau assumed): 95–140 commits, 65–95 merged PRs, +11 000–17 000/−1 500–3 000
  lines, tests ≈45–50% of insertions.
- **Date**: earliest defensible date is 2026-10-11 (the "security fix ≤7 days" rule, 7 days
  after 1.37.0); the realistic window is **2026-10-12 … 2026-10-18**, gated on the release
  steps that 1.37.0 needed (CHANGES date + version bump release commit, docs-site update,
  unitctl tag).
- **Comparability**: the 1.37.1 cycle is a patch cycle, so its churn cannot be compared to
  1.37.0 (a batch-merge release day carrying 211 PRs); the useful comparison is 1.36.1.

## The 1.37.x shortlist (checked 2026-10-11)

A patch release carries security and severe-regression fixes only. Inside that rule
three open issues fit the line, each small enough for one review wave:

- **#537** — http: the body-read deadline restarts on every read, so a slow client
  keeps a request alive indefinitely. Fix: one absolute deadline per request body.
- **#538** — http: route regexes are matched without PCRE2 match, depth or JIT-stack
  limits. Fix: set the limits at match time; a configuration member is optional.
- **#539** — http: the concurrent-connection ceiling is a hardcoded 256. Fix: make
  the limit a known, documented value.

All three carry **no label** today; the label is what the release process reads, so
labelling them is the first step. **Attempted 2026-10-11 and blocked:** the
automation account (the GitHub App used for writes) is installed on
`freeunitorg/freeunit-exp` only — `/installation/repositories` returns exactly one
repository — so it gets 403 creating or applying a label in `freeunitorg/freeunit`.
There is no `z-security` label in the main repository either. Two ways out: install
the App on the main repository, or apply the labels by hand. Until then these three
stay invisible to the release process; the shortlist itself is recorded in the
release-train discussion (freeunit-exp #12) so it is not lost.

Do not hold the 1.37.1 tag for them: ready inside the window they ride with 1.37.1,
otherwise they take the next patch release alone.

**#632** (no 32-bit CI job) is infrastructure, not release content, but it guards the
class that already produced two 32-bit bugfix entries in the 1.37.1 block (the
`off_t` and the size-arithmetic fixes) — worth landing in the same window.

Features that stay out of the 1.37 line: HTTP/2 stack (#463, #467, #470, #471, #479,
#483, #484), router schedules (#452), USDT probes (#451), read-only status socket
(#460), router match extensions (#461), opt-in PCRE2 JIT (#551).

The same shortlist is public in `STREAMS.md` of `freeunitorg/freeunit-exp`
(pull request 21), which is where the stream state lives now.

## What is queued after 1.37.1 (1.38.0 staging)

Open feature PRs ~**+35 200 insertions** staged (TLS 1.3 work joins this window,
priority stated 2026-10-11 — see `engineering/tls-1.3-and-kubernetes.md`): HTTP/2 over TLS stack (#463 stage 1, #467
stage 2, #470 stage 3, #471 fuzz target, #479 h2spec/docs, #483 trailer limits, #484 build
flag), router schedules (#452), USDT probes (#451), read-only status socket (#460), router
match on absent header/cookie/argument (#461), opt-in PCRE2 JIT (#551), Docker Drupal dev
kit (#453), non-blocking perf gates (#449, #450), plus fresh infrastructure work from
Oct 7–8 (#626 reproducible builds, #638 libunit response through the port queue, #643 CI
job reduction, #645 libunit buffer shrink). Tracking issues #443, #596 (PHP worker mode and
Rapira parity waves for 1.38.0) and #597 (performance/bug-fix track) are the declared homes
for this scope.

## Blockers and risks for 1.37.1

- **No Security entry yet** while the 2026-10-03 audit issues stay open: #537 (body-rate
  floor / slow-POST hold), #538 (PCRE2 limits → remote ReDoS), #539 (hardcoded 256
  concurrent-connection ceiling), #540, #541. Hypothesis: either one of these lands and
  makes 1.37.1 a security patch, or the release ships as bugfix-only — which sits outside
  the stated "patch = security/DoS fixes only" policy and is worth an explicit decision.
- #632: no CI job compiles a 32-bit target, so a 32-bit-only `-Werror` survived into 1.37.0;
  the fix is in this cycle but the gate is still missing.
- #624: `test_asgi_websockets_message_over_buffer_limit` hangs on s390x (blocking sendall,
  no timeout) — a flaky-red risk for the release CI.
- Release steps still pending: CHANGES date + `version` bump, docs-site/`changes.xml` polish
  (the 1.37.1 stanza is still dated 2026-10-04 with an empty-looking revision), unitctl tag.
- 20 of 35 open PRs carry no label, and none carries a security label — triage visibility is
  weaker than the queue size suggests.

## Not verified

GitHub security advisories / GHSA drafts were not read: the GitHub token is read-only
without the `security_events` scope. Colour/scope statements above come from labels, PR
titles and `CHANGES` text, not from advisory data.

## Method

`git fetch origin --tags`, `git rev-list --count 1.37.0..origin/master`,
`git diff --numstat 1.37.0..origin/master` bucketed by path family,
`git show origin/master:CHANGES` section parse (entries up to the next "Changes with"),
`git show origin/master:version`, `gh pr list --state open/merged --json ...` and
`gh issue list --state open`. Tag boundaries use committer dates. Physical vs code-line
definitions are in [code-volume-and-release-delta](code-volume-and-release-delta).

## State 2026-10-11 (refresh; supersedes the section above)

- master `4fef769d` ("test: name the descriptor kinds a leak assert found"); still **no
  release commit** — `version` is `1.37.0` / `NXT_VERNUM=13700`.
- Since the 1.37.0 tag: **96 commits**, ~69 merged PRs, 254 files, **+14 189 / −1 698**.
- `CHANGES` 1.37.1 section: **23 entries** (15 on 2026-10-09), section header still
  `04 Oct 2026`; 0 Security entries while the 2026-10-03 audit issues stay open.
- Open queue: **33 PRs**, **62 issues**; milestone **1.37.1 = 11 open PRs + 4 open issues**,
  due 2026-10-30.

### What is left for 1.37.1

| item | state |
|---|---|
| #646 (tests, closes #625) | 🟡 cleared: rebased on the merged #639, head `8cbd5b1c`, 27 checks pass — mergeable |
| #670 (closes #666), #671 (closes #667), #673, #659, #558 | open, ready, **no review note** in the 2026-10-10/11 archive |
| #451 (USDT probes) | needs a changelog entry (feature) in `CHANGES` + `docs/changes.xml` — the only gap |
| #453 (Drupal core dev kit, draft) | pin the Composer SHA-256 as a literal (today the checksum is fetched from the same origin) + changelog |
| #638 (libunit port queue) | head moved past the review: +1819/−162 in 7 files, a third commit closes the missed drain-timeout finding, `test (node-26)` green → **needs a fresh review**, the old verdict does not cover it |
| #551 (PCRE2 JIT), #617 (macOS CI) | drafts |
| #647 (out-of-range level disables compression) | issue only, no PR |
| release mechanics | `version` bump, `CHANGES` date, `changes.xml`, unitctl tag — all pending |
| open decisions | Security entry vs bugfix-only release (contradicts the "patch = security/DoS" policy); #632 (no 32-bit CI job — gate still missing); #624 (s390x) closed |

### Performance track

The authoritative checklist is issue **#597** — waves 0 (1.37.1: s390x rerun + product-bug
vs test-race decision, the 22 old unhyphenated ghcr tags), 4 (IPC cost in worker mode,
K2 first) and 5 (measurement, `type: external` C app as the lab floor). `mp` junk fill is
deliberately **not** in 1.37.1 (two runs inside the null band; branch kept, no PR).
Outside the tracker: LTO/PGO **parked** (resume = rebase `build/lto-option`, run jobs 08/09/10,
continue only if `r_instructions` leaves the 2.5% band), OTel-compiled-but-unconfigured job
written but never run, the libunit message-cost branch (−14.4% vs master, local only, no PR),
the 1.36.1→1.37.0 regression re-measure + bisect, PCRE2 JIT/limits (#551/#538/#545), and
worker mode / Rapira parity (#596).
