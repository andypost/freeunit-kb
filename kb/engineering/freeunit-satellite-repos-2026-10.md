# FreeUnit satellite repos (created 2026-10-10): harness, benchmarks-drupal, research, freeunit-exp

_Read 2026-10-11. Four repos appeared in `freeunitorg` on 2026-10-10; all default branch `main`. Together they are the **public output layer** of the multi-agent loop: a toolkit to work on the server, a benchmark that measures it, a repo for promoted findings, and a bot workbench fork._

## freeunitorg/freeunit-harness — the contributor toolkit

"A contributor toolkit: build, test, CI gates, benchmarks and written procedures." Lives **outside** the server repo so it can move on its own schedule; nothing in it is required to contribute. It clones the server into `./src` (`make src`).

Entry points: `make doctor` (what the machine lacks, changes nothing) · `make dev` (source + configure + build + unitd on :8080) · `make test` (pytest against that build) · `make stop` · `make ci-local` (planned) · `make bench`. **Start a coding agent in the harness dir, not in `./src`** — the server clone has its own git root, so an agent started there gets no harness context.

| Path | What it holds |
|---|---|
| `Makefile` | the entry point; every workflow is a target |
| `AGENTS.md` (`CLAUDE.md` symlink) | agent entry point: traps first, then links into `skills/` and `docs/` |
| `skills/` | Agent-Skills-format procedures, names start `freeunit-`: **build, test, review, verify, release, security, benchmark, cross-arch, debug** |
| `agents/` | one brief per narrow delegated job: adversarial-reviewer, ci-watcher, independent-verifier, packaging-archaeologist, perf-runner, release-orchestrator, remote-builder |
| `docs/` | how the server works + how the harness is run (`docs/README.md` index) |
| `ci/` | `Dockerfile.dev`, `Dockerfile.alpine` for `make ci-local` and `tools/test-isolated` |
| `tools/` | runnable tools; each script's header comment is its documentation |

**Local gates** (`tools/gates/run-gates -s <checkout>`) — six gates, each prints `G<n>: PASS|FAIL`, non-zero exit on failure, and each mirrors a CI job that must be followed when it changes:

| Gate | What | Mirrors |
|---|---|---|
| G1 | `--hardening=strict` build with gcc **and** clang | `hardening-strict` in `build-test.yml` |
| G2 | a build + a pytest slice (`-t`) | `build-test.yml` |
| G3 | ASan/UBSan build, `test_static.py`, log scan via `.github/scripts/check-sanitizer-reports.sh` | `sanitize.yml` |
| G4 | short libFuzzer run on `fuzz_basic` | `fuzzing.yml` |
| G5 | ast-grep rule tests + baseline check (reads `tools/ast-grep/` **from the checkout**; needs ast-grep 0.45.3 as pinned) | `ast-grep` in `lint-astgrep.yml` |
| G6 | `@contract` comment check — **list is empty, checks nothing today**, local only | none |

G1–G4 build, so they refuse to run without `--allow-local-build`; the default set is `5,6`. Rationale: a build belongs on the build host (`tools/unit-build -t remote -H build --hardening tests`), and `./configure` rewrites the root `Makefile`/`build/` of the tree it runs in, clobbering a worktree you are editing.

**Notable tools:** `tools/test-isolated` (since server commit `2149f582` the suite takes `--port N`, so two checkouts on one host run at once without root/docker/namespaces; falls back to the namespace ladder for the two abstract-socket tests and for older checkouts) · `tools/check-public.sh` (fails a commit that carries a private detail) · `tools/build-pack.py` (one text file of router+libunit+port IPC for a long-context model) · the perf lab: `bench-engines.sh` (A/B with a noise floor first), `bench-release.sh`, `bench-crossover.py`, `bench-startup.sh`, `perf-job.sh`, `perf-compare.py`, `perf-bisect.sh` · `tools/task` + `tools/inbox` (task ledger and agent message bus) and `tools/hooks/` (Claude Code hooks, `make hooks-install`).

**`tools/model/` — a behavioural model of the server** (added the day after the import, ~4,000 lines): Model A = deterministic discrete-event simulation of the data path (router engines, port protocol over Unix datagram sockets, shared-memory app queue + chunk allocator, workers running libunit, schedules); Model B = adversarial exploration that interleaves the two channels and injects faults (worker SIGKILL mid-transfer, SHM exhaustion, client RST, process churn) and checks **six invariants**: stream FIFO order, refcount safety on worker teardown, no SHM leak, progress under backpressure, connection lifecycle, framework state isolation. Constants mirror `src/nxt_port_memory.c` and `src/nxt_app_queue.h` (16 KiB chunks, 10 MiB segments, 131,072 queue entries, 31-byte payloads); `tools/model/schema` checks struct layouts against the headers via a tree-sitter extractor. **The model is not the server** — a violation is a claim about the C code, to be traced in `src/` and reproduced with a test before anyone acts.

**`docs/perf/`** is the perf evidence index worth knowing: `drupal-benchmark-plan-2026-10.md`, `perf-lab.md`, `perf-plan-2026-10.md`, `lto-pgo-adoption-2026-10-08.md` + `lto-pgo-runner-configure-args-ab.diff`, `otel-unconfigured-overhead-2026-10-08.md`, `libunit-message-cost-2026-10-08.md`, `loop-invariant-audit-2026-10-07.md`, `precompute-audit-2026-10-07.md`, `pr601-chdir-vs-stat-2026-10.md`, `php-worker-mode-api-survey-2026-10.md`, `rapira-architecture-2026-10.md`, `csrc-map.md`, `review-613-2026-10-08.md`, `yii3-benchmark-*`.

## freeunitorg/benchmarks-drupal — Drupal on three runtimes, measured

Apache+mod_php vs nginx+PHP-FPM vs FreeUnit, on **one pinned box** with the perf-lab method: **null band first, swapped A/B blocks, `schedstat` CPU, `perf stat` counters**, one measurement per claim, and every run directory pins exact image digests and SHAs in `meta.txt` (never bare branch refs). The published page is rendered from committed `results/*/summary.json` — no number is typed by hand.

- Workloads: `drupal-front` (anon, page-cache hit), `drupal-auth` (session cookie, full render), WordPress front + `/wp-cron.php`, and four cron/queue arms: `drush core:cron` vs `GET /cron/{key}`, `drush queue:run` vs `GET /fu-queue-drain/{key}/50`. **The arms are where FreeUnit has a story** — issue 321 (a cron run stranding a visitor's worker) was fixed in 1.37.0, schedules follow in phase 2.
- Decisions already settled: separate repo; `demo_umami` in phase 0; **1.37.0 tarball default plus a master column**; `powersave` governor recorded; **instructions per request** as the headline metric.
- Published while I read (10 runs, 27 result dirs): front-anon **A=freeunit B=nginx-fpm → "B is 7.7% more server instructions per request", outside the null band of 0.1, 12/12 cells agree**; front-auth freeunit vs fpm → B (fpm) 0.6% **less**, 12/12; fpm vs apache → apache 54.7% more; **master vs 1.37.0 front-anon → NO CLAIM (inside the noise)**.
- Publishing: `pages.yml` renders `report/render.py results public/index.html` and pushes `gh-pages`; it deliberately runs **no** benchmarks (shared runners cannot pin cores or read hardware counters). Page: `freeunitorg.github.io/benchmarks-drupal` once `results/` has its first run.

## freeunitorg/research — promoted findings

The public output of the multi-agent loop: per topic a report + the raw data beside it + `meta.txt` with exact SHAs/versions. Flow: `run/agent-findings/<agent>-*.md` (harness, private) → `clean-findings.py` → **a second agent replays the Repro and sets `verified`** → `kb-pending/<topic>.md` → maintainer promotes → `research/<topic>/`. Rules: raw data committed beside the report so every number rebuilds from `data/`; no home paths, hosts, tokens or advisory text (`check-public.sh` semantics). Topics so far: `sessions-tracker/` (proof of path, 2026-10-10).

## freeunitorg/freeunit-exp — the bot workbench (fork of freeunit)

An experimental fork that exists so an unattended bot can open branches, run CI and file PRs **without write access to the release repo**. `HERMES.md` is the rule set: never push to `freeunitorg/freeunit`; `master`/`main` tracks upstream only and is protected; branch names carry the task (`hermes/<topic>`, `hermes/pr-<n>-<topic>`); a change needs the same gates as upstream (test failing on pre-change code with the value quoted, warning-free `--hardening=strict` build, measured numbers, plain English); public only — no embargoed advisories, private notes, hosts or credentials; **CI in the fork is evidence for a review, never a substitute for the upstream CI on the PR**. Upstream sync is a fast-forward (`gh api -X POST repos/<org>/<repo>/merge-upstream -f branch=master`). Its own findings so far: T1 — the PHP option value is string-only, by design; T2 — the Drupal install command owns SQLite and `hash_salt` gates the form (verified against Drupal core). The GitHub App needs `contents/pull_requests/issues: write` + `checks/actions: read` on **this fork and the research repo only**.

### It is the collaboration channel with the cloud agent (verified 2026-10-11)

The fork is the two-way channel: **andypost files tasks as issues**, the cloud Claude agent (**`app/freeunit-agent[bot]`**, a GitHub App with write on this fork + the research repo) answers with work items, `hermes/<topic>` branches, PRs and review notes, and never touches upstream. Inputs arrive as issues (#3/#4/#10 were webhook/react tests; #6 a real task), outputs as issues + PRs.

Current open items on the channel (2026-10-11):

- **issue #11 (bot, open)** — "Rework: follow-ups from the 1.37.1 review archive": 74 PRs of milestone 1.37.1, every line re-checked against the live tracker at `master 4fef769d`. Section A (blocking): #451 ships a feature with **no changelog entry**; #453 verifies Composer against a checksum fetched **from the same host as the binary** (pin the SHA-256 as a literal ARG); #638's head moved past its review (+1819/−162, needs a **fresh review**); #646 cleared (rebased, 27 checks, merge don't rework). Section B is ~18 carried-over small items, each with `file:line` and a named risk.
- **issue #6 (andypost, open)** — the T1/T2 benchmark-verification task; both findings already landed as merged PRs #7 and #8, so the issue is effectively answered and wants closing.
- **PR #5 (bot, open)** — `reviews/PR-645.md`, the first artifact on the workbench: records the revision a review was written against (`3f7a069c`), verdict, findings, verification log. It doubles as the **end-to-end test of the bot's App credential** (push works). Layout assumption: bot output lives in top-level dirs (`reviews/`, later `findings/`, `digests/`). Per HERMES.md rule 2 **the bot does not merge its own PRs**.

**My side of the channel is READ-ONLY.** Verified 2026-10-11: `PATCH /repos/freeunitorg/freeunit-exp/issues/11` → **403 "Resource not accessible by personal access token"** (and the webhooks API is 403 too). The token is the `andypost` PAT, fine-grained, without issues/PR write. So: analysing the agent's output and drafting replies is possible here; **posting a comment, a branch or a PR is not** — anything that must reach the bot goes through the maintainer, or the token needs `issues: write`/`pull_requests: write`. State of the release it tracks: `master` 4fef769d (2026-10-11), 1.37.1 section at **23 entries**, `version` still 1.37.0, tag 1.37.1 not cut.

Watch wired 2026-10-11: `fu-exp-watch.py` (own state in `state/fu-exp-watch.json`, read-only `gh api`, silent when nothing changed), cron **`beda723c07c7`** (`20 */2 * * *`, no_agent, deliver = Andrey DM) — new/updated issues and PRs of the fork reach the DM without re-reading unchanged items.

## Change watching (wired 2026-10-11)

Watermark tracker cron `a642f89c1e0c` (`15 */6 * * *`, no_agent, deliver = Andrey DM) now covers **five** repos: `repo-freeunit-windows`, `repo-freeunit4drupal`, `repo-freeunit-harness`, `repo-benchmarks-drupal`, `repo-research` (config in `change-repos.json`, wrapper `change-track-newrepos.sh`). Baselines recorded 2026-10-11: windows `7756fad0`, 4drupal `5036b43e`, harness `21f5eaa2`, benchmarks `ca0d3f53`, research `c903068f`.

**`freeunit-exp` is deliberately NOT in the watermark tracker**: its `main` mirrors upstream and is fast-forwarded, so every sync would replay the whole upstream delta that `repo-freeunit` already reports (noise, double-advancing the same signal). The interesting signal there is *new `hermes/*` branches and the PRs they open*, which is a branch/PR watch, not a commit watermark.

## Related

- `engineering/windows-port-ci.md` — the port's CI design (harness `docs/` and this repo share the same authors' method)
- `engineering/freeunit4drupal-plan.md` — the Drupal tool whose phase 2 depends on schedules + worker mode (1.38)
- `strategy/freeunit-windows-and-4drupal-repos.md` — the two research/plan repos and their gates
