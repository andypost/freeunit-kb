# zen-quorum: aports gcc MR (main/gcc 16.2.0) — 2026-09-03

_Author andypost — Draft MR. Task: what to do with a draft gcc major-bump MR._

## Ground truth (gathered)
| fact | value |
|------|-------|
| gcc 16.2.0 version | **CURRENT** (no 16.3; released 7 Aug 2026) — version NOT stale |
| aports master | gcc **15.2.0** → MR is a major bump 15→16 |
| MR state | Draft, opened 30 Apr, last updated **8 Aug** (day after 16.2.0) |
| engagement | 0 upvotes, 0 downvotes, no reviewers, merge_status=`cannot_be_merged_recheck` (draft) |
| files | APKBUILD + 9 musl/LoongArch/libsanitizer/ada patches |
| **"stale" meaning** | ACTIVITY (a month of silence), NOT the version |

## Opinion window (2 models)
| model | latent | verdict | rationale |
|-------|--------|---------|-----------|
| laguna-s-2.1-free | 15s (37s) | **C** (close/abandon) | "stale (no activity/votes/reviewers since 8 Aug), lacks integration progress"; a core compiler draft with no reviewer engagement = integration/stability risk |
| ling-3.0-flash-fin-free | 31s | D → (no clean letter) | "version is current (not version-stale), but draft, zero reviews, major 15→16 bump needs active updating + review prep before merge" — reads as B (revive), not C |
| consensus | — | — | **DIVERGENT on the action** (C close vs B revive) but ALIGNED on: version is fine, the MR-as-draft is the problem |

## Interpretation
- Both models agree: **gcc 16.2.0 version is correct** — do NOT downgrade / it is not stale by version.
- Both agree the **draft-with-no-engagement is the real issue** (a month silent, no reviewers, major bump).
- They split on remedy: laguna → **C (close)**, ling → imply **B (revive + prepare)**.
- This is exactly the DIVERGENT case: do not let one model decide. The human (Andrey) is the author — only he knows if the gcc 16 work is abandoned or just blocked.

## Recommendation (hypothesis, not verdict)
Given a **major toolchain bump** (gcc 15→16) sits in a **draft with zero engagement** and the
author is the one who can tell if it's live, the honest path is: **ask Andrey** whether the
gcc 16 work is still active. If yes → revive (B): refresh against current master, resolve the
merge-recheck, solicit a reviewer. If no → close (C) to avoid a stale draft misleading others.
Don't auto-close an author's dormant draft on model opinion alone.

## Next step
The weekly `aports MR weekly (andypost)` cron (Sat 09:30 UTC) already surfaces this MR
as draft. Escalating it to Andrey is the correct action, not a model verdict.
