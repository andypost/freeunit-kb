# Milestone 1.37.1 triage — what ships in the patch, what moves out

_2026-10-12 19:50 UTC (network clock; the session date was a day stale). Evidence:
live `gh api` calls, each item's head SHA vs its last review commit, checks on head.
Our PAT is read-only on both repos (verified: `git push --dry-run` to
`freeunitorg/freeunit-exp` → 403 "Permission … denied to andypost"), so this is a
dossier for Andrey / the workbench bot, not a set of posted comments._

## State

- Live `master` `8492d5ee`; `version` 1.37.0 / 13700; CHANGES top section
  `Changes with FreeUnit 1.37.1   04 Oct 2026` → **26 entries: 23 Bugfix, 3 Change**.
- Milestone **1.37.1: 12 open** (was 15 a day ago), **1.37.2: 4 open**, 1.38: 14.
- Since the previous check: **#646 merged, #625 closed as the duplicate it was**
  (so the duplicate pair is resolved), **#558 merged** (wasmtime C API).

## Triage of the 12 open items

Policy applied: 1.37.1 is a **patch** release (security/DoS and bug fixes only);
a feature cannot ride in a patch whatever its size.

| # | Kind | What | Evidence | Verdict |
|---|---|---|---|---|
| 451 | PR `feat` | USDT probes behind `--usdt` | +287/−0, 22 files, checks 25 ok / 5 skipped, review at head | **MOVE → 1.37.2** (feature) |
| 453 | PR `feat` | Docker Drupal dev-kit image | **base = `feat/schedules`**, draft, +8237/−75, 93 files, 5 commits, checks partly cancelled | **MOVE → 1.37.2** (feature; also stacked on another feature branch, cannot merge to master as-is) |
| 551 | PR `feat` | opt-in PCRE2 JIT | draft, +532/−15, no reviews | **MOVE → 1.37.2** (feature, draft) |
| 617 | PR `ci` | run unitd and serve a request on macOS | draft, 1 file, checks 5 ok | **MOVE → 1.37.2** (CI, not a patch blocker) |
| 685 | PR `ci` | hook gate in the ASan C-tests leg | 1 file, checks 30 ok | move or ride — does not block the tag |
| 666 | ISSUE | compression: first body part uncompressed past ~1 KiB headers | no PR | **fix needed** (bugfix, in scope for 1.37.1) |
| 667 | ISSUE | router: request arriving at startup can hang forever | no PR | **fix needed** (bugfix, in scope) |
| 670 | PR | router: compress the body part sent with response headers | checks 30 ok, **no review** | review + merge |
| 671 | PR | router: publish the engine port before the engine thread starts | checks 30 ok, **no review** | review + merge |
| 659 | PR | lib: keep scanning mountinfo past unrelated cgroup2 mounts | checks 30 ok, **no review** | review + merge |
| 638 | PR | libunit: send the response through the port queue again | **head `8ee100c1` ≠ reviewed `05658304`**, +2067/−162, 7 files, checks 30 ok | **re-review at head**, then decide (size argues for 1.37.2) |
| 683 | PR | port: arm the write event when an inline send queues the rest | **head `44619d55` ≠ reviewed `44df462f`**, +450/−0, checks 30 ok | **re-review at head**, then merge |

## The two findings worth acting on

1. **Two PRs are reviewed at a commit that is no longer their head** (#638, #683).
   The review comments are anchored to the older SHA, so the review does not cover
   what would merge. Both have green checks on head (30 each) — green CI is not a
   review. #638 is the heavier one: **+2067/−162 across 7 files** in a *patch*
   release, touching libunit's response path.
2. **Three features sit in a patch milestone** (#451, #453, #551) plus #453 is built
   on `feat/schedules` rather than `master`, so it is not mergeable to master at all
   until that branch lands. Moving them to 1.37.2 costs nothing and unblocks the tag.

## Ready-to-post texts (plain markdown, English)

For #638:

> The last review is anchored to `05658304`; the head is now `8ee100c1`, so the
> review does not cover the code that would merge. Please re-review at head — the
> change is +2067/−162 over 7 files in the libunit response path, which is large for
> a patch release. If the re-review finds anything structural, this belongs in 1.37.2
> rather than 1.37.1.

For #683:

> The last review is anchored to `44df462f`; the head is now `44619d55`. Checks are
> green on head, but the review predates it — a fresh pass at head is needed before
> merge.

For the milestone (exp issue #11 or a maintainer note):

> 1.37.1 is a patch release, so #451, #453 and #551 (all features, #453 also based on
> `feat/schedules`) move to 1.37.2; #617/#685 are CI-only and do not block the tag.
> The patch is then #666 and #667 (no PR yet), plus the mergeable bugfix PRs
> #659/#670/#671 and #638/#683 once re-reviewed at head.

## Hand-off

Our PAT cannot write here (403 on push; issues/PR writes were already 403). Either
Andrey posts the three texts and moves the milestone, or the workbench bot does —
the command shape is
`gh issue edit <n> --repo freeunitorg/freeunit --milestone 1.37.2` and
`gh pr comment <n> --repo freeunitorg/freeunit --body-file <file>`.

## Related

- `releases/1.37.1-plan.md` — the release plan this triage feeds
- `engineering/freeunit-satellite-repos-2026-10.md` — the workbench fork and its rules
