# OKF KB — handover briefing for another Hermes agent

**Created:** 2026-10-10 (SOUL, for Andrey)
**Purpose:** hand this agent the FreeUnit Knowledge Base — what it is, how to read
and write it, and which files actually need to travel.

---

## 1. What the KB is

Plain **markdown**, no database, no embeddings, no service. Retrieval is
`index.md` + text search + an optional prebuilt relationship graph.

- Format marker: `format: "open-knowledge-format-v1"` in the index frontmatter.
- Three roots, all walked by the same tooling:
  - **kb-freeunit** — the FreeUnit KB (main, 135 `.md`, ~880 KB of content)
  - **kb-shared** — cross-project facts (1 file: `php-deprecations.md`)
  - **kb-mimic** — the Mimic language project (6 files)
- Same server, same user. The KB is files on disk — an agent with a shell and
  read access needs nothing else to use it.

## 2. Layout

| Dir | Files | Content |
|---|---|---|
| `index.md` | 1 | master index — the only entry point; slug + one-line abstract per file |
| `engineering/` | 105 | architecture, protocols, benchmarks, security, ops facts, research |
| `strategy/` | 13 | monetization, funding, promotion, content plan |
| `v1/` | 5 | C-core: overview, architecture, roadmap, release notes |
| `v2/` | 4 | Rust PoC: overview, architecture, liveness, KPIs |
| `releases/` | 4 | fact-checked release announcements (EN/RU) |
| `team.md`, `repos.md`, `history.md` | 3 | attribution, repos/access, timeline |

## 3. Conventions (follow these when writing)

- **Filename = topic slug**, kebab-case, no dates except release/forecast docs.
  One topic per file; extend an existing file before adding a near-duplicate.
- **Index line, extension-less relative link:** `- [slug](dir/slug) — abstract`.
- **Frontmatter is optional** (20 of 142 documents carry it). Known keys:
  `title`, `description`, `tags`, `status`, `updated`, `resources`.
  Non-frontmatter docs start with `# Title` and bold `**Created:**` /`**Source:**` lines.
- **Language: English** for KB content, even when the conversation is Russian.
- **A number is only valid with its definition** inside the same file: code lines
  vs physical lines, churn vs net, author vs committer date, measured vs forecast.
- **Measured analyses are written only after validation** — the method, the
  validation list and the caveats stay in the file, so a later delta is comparable.
- **Forecasts are marked as forecasts**: observed inputs, range, what would falsify it.
- **No PII, no secrets, no credentials** in KB or memory. Technical facts only.

## 4. Reading workflow

1. `index.md` — find the slug by section (Project / v1 / v2 / Engineering /
   Strategy / Releases / Meta).
2. Read the file.
3. Cross-references and "what relates to X": the prebuilt graph
   (`tools/kg.py query "<term>"`, `kg.py vec A6`, `kg.py stats`).
   Nodes: doc, issue, PR, file, topic. Edges: fixes, touches, relates-to,
   depends-on, tests, part-of.
4. Large files: stream them (`tools/memcap.py`). The container has 512 MB RAM —
   a whole-file `read()` of a multi-MB artifact gets the process killed.

## 5. Writing workflow — two writes, always

1. Write/update the **topic file**.
2. Add/update its **line in `index.md`** in the same pass. An entry missing from
   the index is invisible to every future lookup.
3. Only if the adding agent holds a GitHub token: `tools/kg.py build` to refresh
   the graph. Without a token, skip it — query still works on the existing graph.

## 6. Measured integrity (2026-10-10) — read this before trusting the index

- Graph: **142 docs, 679 edges**.
- `index.md`: 113 links; **11 dangle** — ten `engineering/zen-review-pr-*.md`
  entries that were indexed but never written, plus one `kb-mimic/...` path
  written relative to the wrong root.
- **35 `.md` files are not in the index at all** (older research, zen-review
  dumps, some strategy docs).

Consequence: **the index is an entry point, not a manifest.** Always pair it with
a content search over the directory. Do not conclude "not in KB" from the index alone.

## 7. Which files to hand over — by tier

**Tier A — bootstrap, always (~31 KB).** Without these the KB is unusable:
- `index.md`
- `engineering/operating-principles.md` (memory vs KB split, pointer rule)
- `engineering/ops-environment-facts.md` (environment quirks: yt-dlp, uv, cron, tools)

**Tier B — project context, for any agent working on FreeUnit (~51 KB):**
`v1/overview.md`, `v1/architecture.md`, `v1/roadmap.md`, `v1/release-1361.md`,
`v2/overview.md`, `v2/architecture.md`, `v2/liveness.md`, `v2/kpis.md`,
`team.md`, `repos.md`, `history.md`.

**Tier C — task-specific topical files.** For a given job hand over only the
matching `engineering/*.md` plus `index.md` so the agent can find the rest.
Never bulk-copy all 5.6 MB.

**Tier D — tooling, if the agent will query or maintain the KB:**
`tools/kg.py`, `tools/memcap.py`, `tools/gh_cache.py`, `tools/gh_checklists.py`,
`tools/review_ledger.py`.
- With a GitHub token: hand the scripts, the graph rebuilds itself.
- Without one: also pass `.kgraph.json` + `.kgraph_fts.sqlite` (4.6 MB, on disk,
  no network needed) so relationship/full-text queries work offline.

## 8. Do not hand over

- `.env`, `auth.json`, `config.yaml`, keys — never.
- The coordinator's kanban board file — private working state, pass only on purpose.
- `kb-mimic/` and `kb-shared/` — separate project scopes; include only if the
  receiving agent's remit covers them.

## 9. Boundaries the receiving agent must respect

- GitHub token is **read-only**: issues/PRs cannot be created by the agent —
  prepare the text, the owner posts it.
- Only the admin edits config/environment.
- Group chat: no tool output, no file paths, no external links unless asked.

## 10. Acceptance check

```
python3 tools/kg.py stats          # expect: doc 142, edges 679
python3 tools/kg.py query io_uring # expect: engineering/io-uring-* docs
```

If the counts differ, the KB was updated after this briefing — expected, not a fault.
