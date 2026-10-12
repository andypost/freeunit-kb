# zen-review architecture — entity-sliced review + local cache (2026-09-03)

Two scripts that together give a QUORUM-DRIVEN REVIEW LAYER on top of the
quorum toolchain. The client (SOUL / cron) picks an entity and an executor; the
layer gathers context, judges (agent) or collects facts (script), and writes a
KB history so nothing is lost between sessions.

## zen_review.py — single entry point

`python3 tools/zen_review.py --pr 254 --mode agent` / `--issue` / `--commit`.

Slices by **ENTITY**:
| entity | gather | intent |
|--------|--------|--------|
| issue | body + comments + labels | root-cause / scope / status |
| pr | body + files + head + diff | merge judgment, SPOT |
| commit | subject + files + changed symbols | facts / delta, cheap |

And by **EXECUTOR**:
- `--mode script` — deterministic gather, **no LLM** (facts only). For cron.
- `--mode agent` — runs an LLM quorum (reuses `zen_quorum.run_model` +
  `build_prompt`) and records verdicts.

Writes a KB history file `engineering/zen-review-<kind>-<num>.md` per run:
context / tool_calls / findings / verdicts appended (newest on top). This is the
"trajectory" — a later session reads it instead of re-gathering.

Wrappers: `zen-models-profile.sh` (replaces the old misleadingly-named
`zen-models-watermark.sh`).

## gh_cache.py — local GitHub + GitLab snapshots, delta by watermark

`python3 tools/gh_cache.py pull --repo freeunitorg/freeunit --prs --issues`
`python3 tools/gh_cache.py pull --backend gl --project alpine%2Faports --prs --author andypost --state opened`

Holds a local JSON snapshot of issues/PRs/MRs/comments/reviews and, on refresh,
pulls **only the delta** vs a per-item `updated_at` watermark. Mirrors
`change-track` but for **GitHub entity data**, not repo commits.

- **backend `gh`** (GitHub via `gh`): PR↔PR, issue↔issue, comments, reviews.
- **backend `gl`** (GitLab via `GITLAB_HOST=... glab api`): MR↔PR, issue↔issue
  (by `iid`), notes→comments require a token → `_comments_unavailable`.
- **keyless** (GitLab public, no token): lists + diffs work anonymously.
- **watermark prefix** `gh:` vs `gl:` keeps the two backends' watermarks apart.
- **pagination** (`max_pages`), **checkpoint** (save after each item), **`--limit`**
  (batches for huge repos), **stale-break advisory lock** (single-flight, parallel-safe).
- **server-side filters** `--author` / `--state` (`author_username` + `state`) so a
  busy author's list stays current without pulling hundreds.

Verified 2026-09-03: `pull --backend gl --author andypost --state opened` → 9 MRs
(non-draft 2 + draft 7), second pull = "no change" (watermark holds).

## Worked examples in KB
- `engineering/zen-review-pr-254.md` — script + agent history for #254
- `engineering/zen-quorum-aports-gcc-internal.md` — internal patch review (gcc 16.2.0)
- `engineering/aports-andypost-mr-activity.md` — author snapshot

## Related
- `tools/zen-tools-CHANGELOG.md` — the evolving change log for the whole toolchain.
- Skill `zen-quorum` — operating procedure (incl. "trajectory discipline" rule).
