# gh_archive — local GitHub issue/PR/comment archive + FTS search

**Created:** 2026-09-10 (after gateway restore). **Tool:** `tools/gh_archive.py`.

## Why

Searching upstream (nginx/unit, freeunitorg/freeunit) via the GitHub API is slow
and rate-limited (5000 core req/hr; search only 30/hr). A **frozen/archived** repo
is fully static, so **one dump is complete forever** and all later search costs
**zero API calls**. The git history existed for commits; this gives the same for
issues/PRs/comments/reviews.

## What it fetches (repo-wide endpoints = cheap)

| File | Source | nginx/unit |
|---|---|---|
| `issues.jsonl` | `GET /repos/{r}/issues?state=all` (issues **and** PRs) | 1554 |
| `issue_comments.jsonl` | `GET /repos/{r}/issues/comments` (repo-wide) | 8590 |
| `pr_review_comments.jsonl` | `GET /repos/{r}/pulls/comments` (inline) | 2217 |
| `archive.sqlite` | FTS5 index over title/body/comments (porter unicode61) | — |

PR *reviews* (approve/request-changes summaries) have **no repo-wide endpoint** —
not fetched (would be one request per PR). Inline review comments ARE covered.

**Location:** `/opt/data/gh-archive/<owner>__<repo>/` (override: `GH_ARCHIVE_DIR`).

## Usage

```bash
export GH_CONFIG_DIR=/opt/data/.config/gh   # read-only andypost token
python3 tools/gh_archive.py dump   --repo nginx/unit      # one-shot (~90 reqs, ~1 min)
python3 tools/gh_archive.py search --repo nginx/unit "acme cron"
python3 tools/gh_archive.py search --repo nginx/unit --kind comment "certbot"
python3 tools/gh_archive.py search --repo nginx/unit --kind pr "compression"
python3 tools/gh_archive.py stats  --repo nginx/unit
```

`--kind`: all | item | issue | pr | comment | review. FTS5 match syntax supported
(`"exact phrase"`, `term*`, `a OR b`, `a NOT b`).

## nginx/unit archive (2026-09-10)

- **Archived upstream** (frozen 2025-10-08) → the dump is **complete, never stale**.
- Coverage: **1087 issues + 467 PRs**, created **2017-09-06 → 2025-10-08**;
  8590 issue comments, 2217 review comments. Dump ≈ 90 requests.

## freeunitorg/freeunit archive (2026-09-10)

- **Live repo** → snapshot, not frozen. 311 items, 966 issue comments, 555 review
  comments; dumper ran in ~18s, zero rate-limit pressure. Re-run `dump` to refresh.
- Use it for instant offline search of the fork's own history (e.g. the #254 capget
  thread, #304/#316 UTF-8 discussions).

## Pitfalls

- `gh api --paginate --slurp` returns a **list of pages**; flatten one level. The
  dumper does this. Don't `json.loads` the whole stream as one object.
- If the process is interrupted mid-index (leaves `archive.sqlite-journal`), just
  re-run the index build — the JSONL files are already on disk (build_index reads
  them). Delete the stale `-journal` first.
- `search` verbs are `issue`/`pr`/`comment`/`review`, not GitHub's `is:issue`.
- The 30/hr **search** API limit does not apply here — we use the **core** API
  (5000/hr) for enumeration; local FTS does the searching.

## Refresh for a live repo (freeunitorg/freeunit)

That repo is **not archived** → re-dump to refresh (or wire a `change-track`-style
delta later). For a one-off refresh, just re-run `dump` (idempotent: rewrites
JSONL + rebuilds the index).
