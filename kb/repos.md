---
title: "FreeUnit Repositories"
description: "All FreeUnit repositories, forks and related projects"
tags: [freeunit, repos, github, forks]
---

# FreeUnit Repositories

## Primary

| Repository | Description | Default branch |
|------------|-------------|----------------|
| [freeunitorg/freeunit](https://github.com/freeunitorg/freeunit) | **Main LTS fork** of Unit in C | `master` |
| [andypost/unit](https://github.com/andypost/unit) | **Personal fork** for roadmap and drafts | `roadmap` |
| [nginx/unit](https://github.com/nginx/unit) | **Upstream** — archived Oct 2025 | — |

## FreeUnit v2

| Project | Description | Status |
|---------|-------------|--------|
| freeunit2 (PoC) | Rust orchestrator + NTS PHP workers | PoC complete (2026-06-15) |
| freeunit2-fnb | Request.id multiplex (single-in-flight fix) | — |
| freeunit2-a4v | "Fair three-way": v2 vs RoadRunner vs FrankenPHP | — |

## Related

| Repository | Description |
|------------|-------------|
| freeunitorg/trueasync-experiment | TrueAsync experiments (v3) |

## Branch structure of andypost/unit

- `roadmap` — main (plans, drafts before PR to freeunitorg)
- `master` — upstream code
- `pre-1.35.6` — pre-release branch
- `claude/*` — AI-generated PRs
- `p*` — phased items (p1-graceful-signal-split, p2-listener-drain, ...)
