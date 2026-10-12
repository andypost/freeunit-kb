# FreeUnit — code volume and per-release delta (measured 2026-10-05)

Scope: what each FreeUnit release added, measured against the previous release tag,
and how the code base grew/split between runtime code, unit tests and integration
tests. All numbers come from the `freeunitorg/freeunit` clone (tags fetched) plus
GitHub merge/close timestamps — no estimates.

## Method & definitions

- **Release window** = `previous_tag..tag`, boundaries = **committer date** of the
  tag commit (the annotated tag date is not the release date; 1.37.0's tag object is
  dated 2026-10-04 while the release-prep commit keeps its author date 2026-09-25 —
  always use `%cd`).
- **Churn** = `git diff --numstat prev..tag` summed (insertions + deletions; a line
  changed twice counts twice). **Net** = `git diff --shortstat` (text files only;
  binary and rename-only entries are dropped by numstat: 726 text vs 786 total files
  for the whole era).
- **LOC** = `pygount --format=json` (pygount 3.2.0) `codeCount`, i.e. source lines
  with blanks, comments and string-only lines removed. Snapshots extracted with
  `git archive <tag> | tar -x`.
- **Commits** = `git rev-list --count prev..tag`.
- **PR / issues** = `gh pr list --state merged --json mergedAt` (381 rows, well under
  the 1000 cap → not truncated) and `gh issue list --state all` (131 rows), bucketed
  by `mergedAt` / `closedAt` / `createdAt`.
- Tags used: `1.35.0` (upstream NGINX Unit, 2025-08-26) as baseline, then
  `v1.35.1`, `1.35.2`, `1.35.3`, `1.35.4`, `1.35.5`, `1.36.0`, `1.36.1`, `1.37.0`.

## Code-size split (pygount code lines)

| Category | 1.35.1 (03.04.26) | 1.37.0 (04.10.26) | Δ |
|---|---|---|---|
| runtime C (`src/` без `src/test/`) | 65 614 | **70 682** | +5 068 (+7.7%) |
| unit tests C (`src/test/`) | 3 020 | **17 796** | +14 776 (×5.9) |
| integration tests Python (`test/`) | 15 400 | **27 162** | +11 762 (+76%) |
| unitctl Rust (`tools/`) | 3 657 | **4 889** | +1 232 (+34%) |
| docs / pkg / CI / meta | 6 065 | **7 628** | +1 563 |
| **tree total** | **107 805** | **142 666** | +34 861 (+32%) |

Composition shares of tree code: runtime C 60.9% → 49.6%; tests (C+Python)
17.1% → **31.5%**; tests-to-runtime ratio 0.28 → **0.64**.
Physical-line anchor (all lines, both trees): runtime core 147 010 → 165 956;
tree total 213 504 → 306 414.

Other languages in the 1.37.0 tree (code lines): C 89 931, Python 23 598,
Java 12 426, Rust 5 818, YAML 5 642, JavaScript 1 619, Bash 1 023, C++ 714.
`src/` outside `src/test/` also carries the Java module (22 143 physical lines)
and `src/otel` (Rust) — "runtime C" above is the C/H part only.

## Per-release churn, split runtime vs tests

| Release | days | commits | PR merged | issues closed | runtime C | unit tests C | integration tests | unitctl | meta | total |
|---|---|---|---|---|---|---|---|---|---|---|
| 1.35.1 | 220\* | 30 | 4 | 0 | +4/−1 | +2/−2 | +15/−1 | 0 | +698/−373 | +719/−377 |
| 1.35.2 | 0 | 41 | 11 | 0 | +1 123/−36 | 0 | +647/−0 | +20/−20 | +762/−265 | +2 552/−321 |
| 1.35.3 | 2 | 6 | 1 | 0 | 0 | 0 | 0 | +7/−9 | +800/−106 | +807/−115 |
| 1.35.4 | 23 | 41 | 13 | 0 | +19/−12 | 0 | +797/−21 | 0 | +1 519/−651 | +2 335/−684 |
| 1.35.5 | 29 | 9 | 12 | 5 | +225/−20 | 0 | +1 012/−34 | +26/−19 | +3 580/−230 | +4 843/−303 |
| 1.36.0 | 48 | 139 | 56 | 4 | +4 795/−2 678 | +1 335/−0 | +6 063/−47 | +1 473/−1 585 | +5 368/−1 271 | +19 034/−5 581 |
| 1.36.1 | 42 | 99 | 69 | 9 | +4 632/−1 366 | +2 769/−7 | +3 788/−60 | +148/−13 | +1 656/−155 | +12 993/−1 601 |
| 1.37.0 | 36 | 314 | 211 | 68 | +21 721/−9 457 | +26 390/−691 | +16 211/−969 | +2 483/−706 | +9 445/−699 | +76 250/−12 522 |
| **Σ** | 184 | **679** | **377** | **86** | +32 519/−13 570 | +30 496/−700 | +28 533/−1 132 | +4 157/−2 352 | +23 828/−3 750 | +119 533/−21 504 |

\* 1.35.1 row is the gap from upstream 1.35.0 (Aug 2025) to the first FreeUnit release,
so its "days" is not a FreeUnit cycle.

Per-release commit counts are the **uncapped** `git rev-list --count` (the digest's
commit list is capped at 40 and must never be used as a count).

Era totals: **679 commits**, **377 merged PRs**, **86 issues closed** (131 opened,
45 still open), churn Σ +119 533/−21 504, **net +114 747/−16 718** over 786 files.
Churn exceeds net by 4 786 per side — exactly the lines rewritten in more than one
release window (Σadd−Σdel = net add−net del = +98 029, so the two views agree).

Only 4 PRs have been merged since 1.37.0 (window still open at measurement time).

## Fraction of the code base (the headline ratios)

- 1.37.0 cycle: churn 88 772 lines = **126% of the runtime C base** (70 682), 62% of
  the tree; net additions +63 728 = **90% of the runtime C base**.
- 1.37.0 insertions are **55.9% tests** (42 601 of 76 250): src/test +26 390,
  test/ +16 211.
- Whole era (1.35.0 → 1.37.0): net +98 029 = **139% of runtime C**, 69% of the tree;
  churn 141 037 = **200% of runtime C**.
- Yet runtime C grew only **+7.7%** in the same era. The code base rewrote itself
  roughly twice over to add ~5k net lines of runtime code — churn is dominated by
  rework and by the test suite, not by new runtime code.

## Validation performed

1. Per-interval `rev-list --count` sums to 679 = `rev-list --count 1.35.0..1.37.0`. ✓
2. Per-release PR buckets sum to the era total and the full `gh` list size
   (4+373 = 377; +4 after 1.37.0 = 381 rows fetched). Issue buckets sum to 131 = all
   rows fetched → every issue in the tracker was created inside these windows. ✓
3. Category churn sums equal `git numstat 1.35.0..1.37.0` totals; the 60-file
   difference against `--shortstat` is binary/rename-only entries. ✓
4. Two independent LOC measures agree in direction and are documented as a range:
   pygount 70 682 vs a naive non-blank/non-comment counter 87 727 on the same
   `src/` (excluding tests) — the naive counter classifies some comment/blank
   constructs as code (+23% on `src/`, verified per-file on `nxt_router.c`:
   5 586 vs 4 625 code lines). Quoted LOC is always pygount; physical-line counts
   are given separately as a third anchor.
5. `gh` lists are below their fetch caps, so no silent truncation; timestamps are
   server-side merge/close times, commit counts are git-side.

## Caveats — what these numbers are not

- Churn ≠ growth. Additions+deletions double-count rework and throwaway edits; only
  the net column describes growth.
- LOC by language counts whole files: the Java module and `src/otel` live inside
  `src/`, so "runtime C" must be read as the C/H part of `src/` outside `src/test/`.
- Release boundaries are committer dates: work merged after a tag but before the next
  release lands in the next window, which is exactly why 1.37.0 (a batch-merge
  release day, 27 PRs merged on 2026-10-04) shows 211 PRs.
- The 1.35.1 window spans the upstream-to-revival gap (Aug 2025 → Apr 2026) and is
  not comparable to the later cycles.
