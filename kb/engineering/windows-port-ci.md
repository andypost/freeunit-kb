# Windows port — CI design (freeunit-windows, from docs/plan.md D16 + research §3)

_Read 2026-10-07 from `freeunitorg/freeunit-windows` at `5b7b078`. **No CI exists yet**: the repo holds only `README.md`, `LICENSE`, `docs/`, `research/` — no `.github/`, no `ci/`. Everything below is the designed pipeline (plan D16) plus the evidence for it (research/toolchain-packaging-demand.md §3.1–§3.7). Durations for FreeUnit are the plan's estimates, not measurements._

## What lands where

| Path | Repo | What it is |
|---|---|---|
| `ci/windows.yml` | **freeunit** | the workflow proposed for the main repo (D16) |
| `.github/workflows/experiments.yml` | freeunit-windows | builds and runs the Phase 0 experiments on hosted runners |
| `matrix/feature-matrix.md` | freeunit-windows | Tier 3 feature matrix, kept in step with releases |
| `decisions/g0.md`, later gates | freeunit-windows | gate records, raw counts so anyone can recompute |

The main `freeunit` repo today has 16 workflows and **no Windows one** (verified 2026-10-07): `build-test.yml`, `build-test-macos.yml`, `build-deb.yml`, `build-distros.yml`, `release-docker.yml`, `unitctl.yml`, `fuzzing.yml`, `sanitize.yml`, `security-seccomp.yml`, `security-syscalls.yml`, `audit.yml`, `eol-check.yml`, `rust-version.yml`, `analysis-clang-ast.yml`, `lint-whitespace.yml`, `claude.yml`. `windows.yml` borrows the path filters of `build-test-macos.yml` (`configure`, `auto/**`, `src/**`, plus `test/**` here).

## The workflow (D16)

Four legs; **every action pinned by SHA, every leg on Node 24, no job uses `windows-latest`**:

| Leg | Runner | What it does |
|---|---|---|
| **win-core** | `windows-2025` (VS 2026 = early warning of D1) | MSYS2 via `msys2/setup-msys2` (SHA-pinned); MSVC env from `vswhere` + `vcvarsall.bat` in one PowerShell step (no third-party action); vcpkg with `VCPKG_BINARY_SOURCES=clear;files,<dir>,readwrite` + `actions/cache` keyed on vcpkg commit/triplet/manifest hash; `./configure --tests`, `make`, `build/tests`; `build/autoconf.err` + logs uploaded as artifacts |
| **win-php** | `windows-2022` (VS 2022 = the release toolset of D1) | PHP 8.5 NTS zip + devel pack, verified against `sha256sum.txt`, cached; module build; pytest smoke subset over TCP control |
| **mingw-cross** | `ubuntu-24.04`, optional | compile-only core build with `x86_64-w64-mingw32` and `-Werror`. **Delete it if it fails for MinGW-only reasons more than twice in a quarter** |
| **nightly** | — | wide pytest subset in 2–4 shards; thread-safe PHP compile; release package on `windows-2022` with a smoke test (unzip, start, one request) |

Rejected: Wine (no usable AF_UNIX upstream; runs a different toolchain), self-hosted runners, larger runners (billed even for public repos), pytest through WSL interop (would test the Linux binary).

**Promotion rule:** Windows jobs are **non-required until 14 days green**; then win-core becomes required, and win-php becomes required after the first demo.

## Runner facts (October 2026, research §3.1)

- Labels that matter: `windows-2025` (also `windows-latest`), `windows-2022`, `windows-11-arm`; VS 2026 moved onto `windows-2025`/`windows-latest` in June 2026, `windows-2022` keeps VS 2022 17.14. `windows-2019` retired 2025-06-30.
- Public repos: 4 vCPU / 16 GB RAM / 14 GB SSD on every standard Windows label (x64 and arm64); private: 2 CPU / 8 GB.
- `windows-latest` **changed twice in nine months** (Server 2025 in Sep 2025, VS 2026 in Jun 2026) → pin explicit labels in required checks; never `windows-latest`.
- Open conflict in the evidence: the `windows-11-arm` image readme still showed VS 2022 17.14 on 2026-09-27 while the VS 2026 move was announced for late September — treat `windows-11-arm` as a nightly leg until it settles, or pin `windows-11-vs2026-arm`.
- Cost: standard Windows runners are **free for public repositories**; larger runners are not; the announced $0.002/min self-hosted platform charge was postponed, not cancelled. Binding limits are wall time and concurrency, not money.

## Tooling traps (research §3.3)

- **Do not use `ilammy/msvc-dev-cmd`** — no push since 2024-04 and it declares `node20`, retired September 2026. Use `TheMrMilchmann/setup-msvc-dev` or call `vcvarsall.bat` directly.
- **vcpkg's `x-gha` binary cache provider was removed in April 2025.** Use the `files` provider + `actions/cache`, or NuGet on GitHub Packages. Cache keys cannot be shared between x64 and arm64.
- PHP comes from windows.php.net NTS zip + devel pack, checksum-verified and cached keyed on PHP version/arch/TS/toolset; `php-windows-builder` builds PHP 8.4/8.5 with VS 17 on `windows-2022` and has `run-tests`/`test-runner` inputs.

## Durations (precedent, research §3.4)

- Comparable C projects: **2–9 minutes** per Windows build+test leg (curl, libuv); PostgreSQL splits its VS leg into 2 slices of ~16 and ~17 minutes.
- PostgreSQL dropped Cirrus CI on 2026-06-04 — its Windows jobs are GitHub Actions now.
- Estimates for FreeUnit (unmeasured guesses): win-core 5–10 min, win-php 10–20 min, win-arm64 8–12, wide pytest 15–20 per shard, package 5, mingw-cross 1–4.
- Shard the pytest leg once it passes ~20 minutes (PostgreSQL precedent).

## Windows test harness (research §3.7 + D14)

1. Import hygiene (`fcntl` off Windows, `pwd`/`grp` behind markers, `getattr(socket,'AF_UNIX',None)`) and a `unix_only` pytest marker applied per file → the target is the 68 test files that match no Unix-only pattern.
2. One platform module in `test/unit/` providing `spawn()`, `stop_graceful()`, `kill_tree()`, `alive()`, `children()`, `count_handles()`, `control_address()`; `conftest.py` (1,036 lines) calls only these. **Rule: Windows branches live in the platform module only** (otherwise they rot).
3. Control over TCP loopback (`--control 127.0.0.1:<random port>`); a separate small C client test covers the product's own AF_UNIX channel, because CPython 3.13/3.14 have no `socket.AF_UNIX` on Windows.
4. Process trees via a Job Object with `KILL_ON_JOB_CLOSE` (ctypes), psutil for scans, `taskkill /T /F` last resort; handle-count **deltas** instead of descriptor counts; collect `unit.log` + crash dumps on failure; `DIE_ON_UNHANDLED_EXCEPTION` so a crash ends the process instead of opening a dialog.
5. Stages: compile-only → C table → pytest smoke over TCP → PHP tests → TLS/proxy/access-log modules.
6. `nxt_test_in_child()` re-runs the test binary with `CreateProcessW` on Windows (no fork); Unix-only tests are compiled out and counted as skipped.

## Rules and gates attached to CI

- **No Windows change merges with Linux or macOS CI red** (plan §8 rule 2); port/process/SHM changes need a second reviewer.
- Risk R4: Linux CI stays required and port-layer PRs get the io_uring harness A/A check — any Linux regression beyond A/A noise blocks the PR, no exceptions.
- Risk R10: a scheduled job watches `https://windows.php.net/downloads/releases/releases.json` and rebuilds the bundled PHP zip; **stop condition: a PHP security release not repackaged within 14 days, twice in a row → stop shipping the PHP module until the job works**.
- Defender: test legs disable real-time monitoring (PostgreSQL precedent, `pg-ci.yml`) because it slows legs and makes renames fail at random; **one nightly job keeps it on**, because developer machines run with it on (D22). Effect size unmeasured.
- Wine is rejected as a test platform; results must stay public-safe (no private host names, no local absolute paths, no credentials).

## Gaps to measure

- Cold vcpkg build time (openssl, pcre2, zlib, brotli, zstd) on `windows-2025` — unmeasured.
- Real FreeUnit leg durations (the table's numbers are estimates).
- Queue latency for Windows and arm64 runners.
- Whether `windows-11-arm` runs VS 2026 now; whether pywin32 is preinstalled; concurrent-job limits for a Free GitHub org (read "Actions limits" before sizing a matrix).

## Related

- `ci-pipeline-balance.md`, `dependency-ci-hygiene.md` — main-repo CI economics and dependency-update hygiene
