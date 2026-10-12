# diff-symbols POC — understand code logic through PRs (2026-09-04)

_What the Mimic agent needs to read code faster and EXACTLY: not a full AST
index of every file (changes rarely, expensive), but a **diff-symbols** table —
which symbols each PR touched and WHY. This is language-agnostic (diffs are
text) and gives evolution, not snapshot — the thing a reviewer actually wants._

## Why this beats a full AST index

| Approach | Cost | What it tells you |
|----------|------|-------------------|
| Full AST index of all files | index 141 files (rare changes), heavy | snapshot: "what exists" |
| **diff-symbols (PR-based)** | incremental via watermark, cheap | **"which PR touched X and WHY"** — the logic |

The insight: to understand a codebase you ask **how it evolved**, not what it
contains. Renames/moves/removals/reasons live in PR diffs + body/comment/issue
context — exactly what a static snapshot hides.

## Storage schema (from POC B — subagent, validated)

```sql
CREATE TABLE IF NOT EXISTS diff_symbols(
    symbol     TEXT NOT NULL,          -- fn/var/class name
    file       TEXT NOT NULL,          -- path in repo
    pr_id      INTEGER NOT NULL,       -- PR number (or commit id)
    pr_title   TEXT,
    delta_type TEXT,                   -- added / modified / deleted / renamed
    lang       TEXT,                   -- c / php / ...
    meta_json  TEXT,                   -- {"body":..., "commit_msg":..., "comment":...}
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, file, pr_id)
);
CREATE INDEX idx_ds_symbol  ON diff_symbols(symbol);
CREATE INDEX idx_ds_file    ON diff_symbols(file);
CREATE INDEX idx_ds_pr      ON diff_symbols(pr_id);
CREATE INDEX idx_ds_delta   ON diff_symbols(delta_type);
CREATE INDEX idx_ds_prefix  ON diff_symbols(symbol, file);   -- subsystem nav
```

**Incremental fill (watermark, no full re-read):**
```sql
last = SELECT max(pr_id) FROM diff_symbols;
new  = SELECT * FROM gh_cache WHERE pr_id > :last AND repo = :repo;
-- for each PR: parse diff with tree-sitter, classify delta, INSERT OR REPLACE
```

**Mimic queries:**
- "which PRs changed a function X and why" —
  `SELECT pr_id, pr_title, delta_type, json_extract(meta_json,'$.body') FROM diff_symbols WHERE symbol='X' ORDER BY pr_id DESC`
- "who else touched this subsystem" — `WHERE file LIKE 'src/db/%' OR symbol LIKE 'DB_%'`
- "rename tracking" — self-join on `delta_type='renamed'` across `symbol`/`file`/`pr_id`

## Real POC on unit (commit 73cc8cc8, src/nxt_application.c)

```diff
+ static void nxt_app_new_port_handler(nxt_task_t *task, nxt_port_recv_msg_t *msg);
-      .new_port = nxt_port_new_port_handler,
+      .new_port = nxt_app_new_port_handler,
+ static void nxt_app_new_port_handler(nxt_task_t *task, nxt_port_recv_msg_t *msg) {
+     nxt_port_new_port_handler(task, msg);
+     nxt_port_recv_msg_close_fds(msg);   // <-- reason
+ }
```

| symbol | delta_type | why |
|--------|-----------|-----|
| nxt_app_new_port_handler | **added**  | close queue fds the base handler leaks (discovery/proto didn't know if they map queues) |
| .new_port | **modified** | point handler to new wrapper (×2) |
| nxt_port_new_port_handler | referenced | stays; called by wrapper |

**Lesson:** the diff comment IS the reason ("only the caller knows whether this
process maps port queues"). That context is in the PR/diff, NOT in a snapshot.

## cache-bounding (POC C — measured 2026-09-04)

- gh_cache.json **224 KB** now (10 entities: 5 PR + 5 GL-MR).
- Full diff of one unit commit (all files) = **29.9 KB**; median PR diff ~**18 KB**.
- Adding a FULL diff for 200 PRs → **+3.5 MB** (16x growth) — too much.
- **Recommendation:** store metadata (title/body/comments/reviews/additions/
  deletions) always; store diff **COMPRESSED** — only `changed_files` + `+/-
  lines` (1–3 KB/PR), NOT the full patch; keep the full patch as a `diff_url`
  link + symbol signatures. Put the diff-symbols table in SQLite separately so
  the meta JSON cache doesn't bloat.

## Toolchain facts (verified)

- tree-sitter-c (uv, wheel, no rust/gcc): parses unit 141 files / 0.9s / 1935 funcs
  — error-tolerant (pycparser 0/141 — fails on macros, needs preprocessor).
- Subagent `zen_tool_agent` gained: retry-on-503 (free-tier availability),
  `run_git` (read-only git, sanitized vs pipe/`;`/redirect — model adds those,
  would break the non-shell subprocess).
- free-tier (2026-09-04): laguna+ling alive/fast, nemotron-3.5 slowed 2x,
  nemotron-3-ultra timeout, deepseek/muse down. Working quorum pair = laguna+ling.

## Related
- `engineering/evolver-reference.md` — the proven parent pattern (symbols+SQLite).
- `engineering/unit-code-graph.md` (next) — tree-sitter symbol index for unit.
