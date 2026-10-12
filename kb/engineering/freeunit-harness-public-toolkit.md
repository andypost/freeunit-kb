---
title: "freeunit-harness — the public contributor toolkit"
description: "freeunitorg/freeunit-harness: what the published repo contains, what it binds contributors to, and how it maps onto our own lanes"
format: "open-knowledge-format-v1"
updated: "2026-10-10"
maintainer: "andypost"
---

# freeunit-harness (public, published 2026-10-10)

Explored 2026-10-10 at commit `6edb775a` ("freeunit-harness: initial public import").
The repo is a **fresh, squashed public import**: one commit, no history rewrite
(`docs/public-harness-plan.md` §2 explains the decision — every private line was also in
HEAD, so a rewrite buys nothing and leaks on the first miss). The private working repo
stays unremote'd.

## Shape

| Fact | Value |
|---|---|
| repo | `freeunitorg/freeunit-harness`, public, Apache-2.0, default branch `main` |
| created | 2026-10-10 21:29Z; single commit, author Andy Postnikov |
| size | 3.2 MB, 234 files, **no workflows, no issues, no PRs** |
| entry points | `Makefile` (249 lines, ~25 targets), `AGENTS.md` (193 lines), `CLAUDE.md` → symlink to it |
| skills | 9, in Agent Skills format (`name` + `description`): freeunit-{benchmark,build,cross-arch,debug,release,review,security,test,verify}, each with `references/` |
| agent briefs | 7 narrow roles + generated twins in `.claude/agents/` and `.opencode/agents/`: ci-watcher, adversarial-reviewer, independent-verifier, release-orchestrator, remote-builder, packaging-archaeologist, perf-runner |
| docs | 22 pages, 13 of them under `docs/perf/` (perf-lab, drupal benchmark plan, LTO/PGO, OTel overhead, pc2/JIT, …) |
| tools | 39 (`tools/task` ledger, `tools/inbox` bus, `tools/check-public.sh`, `tools/gates/run-gates` G1–G6, `tools/perf-*`, `tools/session-extract/*`, `tools/unit-build`, `tools/test-isolated`) |
| perf lab | `tools/perf-lab/` with 34 `.job` files and patches |
| boundary | `run/` (server notes, `run/ghsa/`, raw bench data), the plaintext deny list, the HMAC key and the model price table stay private forever |

## What it binds contributors to

- `docs/agent-coordination.md` §2 is a three-tier authority table: *on its own* / *named job
  from the maintainer* / *Claude only*. Push, force-push and posting on GitHub are in the
  third column; `docs/` and `skills/` are maintainer-only (agents may send a patch).
- Findings pipeline: `run/agent-findings/<agent>-<date>-<topic>.md` → `tools/clean-findings.py`
  → a second agent replays the Repro and sets `verified` → `kb-pending/<topic>.md` → maintainer
  promotes, weekly, one page per commit, finding named in the body.
- `AGENTS.md` says the four pages `review-pipeline.md`, `model-routing.md`,
  `context-priming.md` and `agent-coordination.md` "describe the maintainer's own Claude setup.
  They are background, not instructions for you."
- Rules that cost hours when skipped, from `agents/README.md` (each dated, each from a real
  incident): name the revision you read; "verified" must name the external fetch or the executed
  command; a watch is something you finish, not something you start; every loop gets a deadline
  and a liveness check; agents share one checkout — disjoint files, no git state; every report
  ends with what you could not verify. `AGENTS.md` adds: never build in a checkout you are
  editing, `*:8080` is host-wide and `--port N` since `2149f582` is the fix, cloud machines you
  start are yours to delete (name, owner tag, expiry, delete IP **and** volumes).

## What we verified by running it

- `tools/check-public.sh --all` → exit 0 on the published tree. Its own fixtures:
  `uv run --with pytest pytest tools/tests/test_check_public.py` → **14 passed, 17 subtests**.
- The same gate over **our** `freeunit-exp` content (`reviews/PR-645.md`, `findings/T1-php-option-type.md`,
  `findings/T2-drupal-drush-install.md`) → **exit 0**. The maintainer's own scrub rules accept
  what we publish in the workbench.
- The HMAC layer of `docs/public-harness-plan.md` §3 is **not implemented** (TODO in the script
  header): only the generic ERE rules in `tools/public-deny.txt` + `public-allow.txt` run today.

## Relationship to our lanes

- **The Hermes bot is absent from the public harness.** `rg` for
  `hermes|freeunit-agent|freeunit-exp|workbench` over the tree: **0 hits**. The bot lane lives in
  the private side (`HERMES.md` in the fork, `research/`, and the harness's private `run/`).
- **Policy tension worth reconciling in one line each.** `agent-coordination.md` §2 puts push and
  GitHub posting in the *maintainer-only* tier; `HERMES.md` in `freeunit-exp` grants the bot
  branches and PRs *inside the fork*. Both are the maintainer's documents, one is explicitly
  "background, not instructions" — say which governs.
- **Name collisions with our own skills.** The harness ships `freeunit-benchmark`, `freeunit-review`,
  `freeunit-test`, `freeunit-release`, `freeunit-verify`; we have Hermes skills with overlapping
  names but different content (ours: Scaleway orchestration, PR verification against real branch
  code, PHP stand, Docker ops). Loading the wrong one is the failure mode.
- **CI is not there yet.** The plan phases put `check-public`, `agents-check` and `shellcheck` in
  phase 2 (2026-10-12 → 2026-10-18); today the repo has no workflows, so the gate is local-only and
  we must call it ourselves.
- **Tooling we can reuse as-is** (all python3-stdlib or shell, verified working):
  `tools/check-public.sh` as a pre-push gate for workbench branches, `tools/gates/run-gates` (G5/G6
  need no build; G1–G4 refuse without `--allow-local-build`), `tools/watch-run.sh` for "is this run
  terminal yet", `tools/new-failures.sh` for regression deltas.

## See also

- `references/gh-identity-plan.md` in the `freeunit-github-ops` skill — the workbench fork, the
  App identity and the credential tooling that this repo's rules now sit beside.
