# Operating Principles: Memory vs Knowledge Base Separation

**Author:** Andrey (andypost)  
**Rule:** Memory is NOT a mini-KB. Two stores, two purposes.

---

## MEMORY.md (~2200 char limit)

**Purpose:** Tiny long-lived facts only — preferences, ports, keys, IDs, environment config.

**Allowed:**
- User preferences (verbosity, language, style)
- Tool quirks and workarounds
- Port numbers, hostnames, SSH keys, API tokens
- Repo clone paths, worktree locations
- Telegram group config (require_mention, chat IDs)
- Infrastructure config (Hetzner, Scaleway, OpenRouter)

**NOT allowed:**
- Project architecture summaries (→ KB engineering/)
- Strategic plans, monetization targets (→ KB strategy/)
- Team attribution, commit counts (→ KB team.md)
- Codebase stats, benchmark numbers (→ KB engineering/)
- Release notes, changelogs (→ KB releases/)
- Roadmap items, KPIs (→ KB v1/ or v2/)

**Rule of thumb:** If it helps the agent *find the right KB file*, it belongs in memory. If it IS the content that the agent should read, it belongs in KB.

---

## OKF KB (Knowledge Base — no char limit)

**Purpose:** Everything substantive — architecture, statuses, dumps, summaries, comparisons, research.

**Subdirectories:**
- `engineering/` — Architecture deep-dives, benchmarks, security, protocols, related projects
- `v1/` — FreeUnit v1 (C-core) overview, architecture, roadmap, releases
- `v2/` — FreeUnit v2 (Rust PoC) overview, architecture, liveness, KPIs
- `strategy/` — Monetization, content plan, open-core models, harness
- `releases/` — Release announcements (fact-checked)
- `team.md` — Team structure and attribution
- `repos.md` — Repository layout and access
- `history.md` — Project timeline
- `index.md` — Master index

---

## The Pointer Rule

Memory contains **exactly one line** per KB topic — a pointer, not a summary:

```
KB: v1/architecture — C-core stats (265k LOC buran, 141k freeunit, ~13k RPS)
KB: team.md — team attribution and commit counts
```

This tells the agent *where to look* without duplicating content. If the KB file is missing or outdated, create/update the KB file — don't expand the memory entry.

---

## Enforcement

- Cron jobs and skills that load KB content must reference files by path, not by memory content.
- If a fact changes (e.g. new LOC count), update the KB file. The memory pointer stays the same.
- If memory runs out of space, prune stale env config before trimming KB pointers — KB pointers are the most valuable content in memory.
