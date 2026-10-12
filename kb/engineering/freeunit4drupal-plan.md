# freeunit4drupal — plan and the FreeUnit-side asks

_Read 2026-10-07 from `freeunitorg/freeunit4drupal` at `9dd42318` (default branch `main`). Research + plan only: no code, no CI, no workflows. All sizes are judgement estimates; there is no prototype._

## What it is, and the conditions

A Docker-free local Drupal environment: **one Go binary that supervises one FreeUnit instance per user** for all projects; matched PHP 8.3/8.4/8.5 builds; `<project>.localhost` over HTTP/HTTPS from a local CA; host MariaDB/MySQL or SQLite; Mailpit for mail; **live `.ddev/` config import** so a team can run it beside DDEV. Linux + macOS (Apple Silicon) first; Windows via WSL2 until the native port exists.

**Conditional go** — three conditions:
1. Phase 0 **E1** (build a FreeUnit PHP module against a static-php-cli shared libphp), **E2** (two PHP minor versions in one unitd), **E3** (one broken project must not break the shared reconfiguration) pass by **2026-10-30**, or their fallbacks are accepted.
2. **Two named maintainers** commit through the beta by **2026-10-30** (M0 gate).
3. **macOS milestone M6 starts only after FreeUnit tags a release with the Apple Silicon fix — 1.37.1 or later.**

If part 1 fails without fallback, or part 2 is missed: do not start the tool — contribute the shared Drupal route template to FreeUnit + DrupalCI instead (optional DDEV add-on track T1).

## The FreeUnit-side asks (plan §7 — what maintainers must decide)

Ordered as the plan lists them; status verified 2026-10-07 against the main repo.

| # | Ask | Size | Status |
|---|---|---|---|
| 1 | **Tag 1.37.1 with the Apple Silicon shm fix** | release work | fix merged (#598, 2026-10-07T03:35Z); **tag still missing** — blocks M6 |
| 2 | **CI: build the PHP module + run PHP tests on macOS** | 40–100 lines of workflow + unknown test fixes | half done: C tests landed (#602, merged 2026-10-07T04:16Z), but the macOS job still says "No modules, no pytest, no sudo" — **that gap is how the Apple Silicon failure reached a release** |
| 3 | php: apply `options.admin` before `php_module_startup()` (`zend_extension`, `opcache.jit`, `xdebug.mode` have no effect now) | 60–120 lines + tests | not started (upstream nginx/unit #785, #969) |
| 4 | application: honour per-app `stdout`/`stderr` with `--no-daemon` (`nxt_app_set_logs()` returns early when not daemon) | 3–10 lines + ~40-line pytest | not started |
| 5 | router: merge schedules (Drupal cron without an external timer) | review only | PR #452 open, self-describes as **1.38.0**; milestone 1.37.1 lags the description |
| 6 | http: optional reason on server error pages | 150–300 lines | not started |
| 7 | packaging: FreeUnit formulas in the Homebrew tap (tap still builds NGINX Unit 1.34.2 / PHP 8.4.2) | 150–250 lines of Ruby | not started |
| 8 | drupal: one tested route template for CI, dev kit, howto and local tools (three configs differ today; the howto lists `core/authorize.php` removed in Drupal 12) | 200–400 lines JSON + tests | PR #453 carries the Drupal dev-kit image |
| 9 | static: add `.wasm`, `.map`, `.webmanifest`, `.csv` to the MIME table | 3–6 lines + test | open issue #559 — comment, don't duplicate |
| 10 | access log: per-listener or per-route access log (today one global log) | 200–400 lines | not started |
| 11 | runtime: use or remove inherited `LISTEN_FDS` sockets (the collect loop is `for (s = 3; s < n; s++)` with `n` = socket count, so it takes none/one) | 30–150 lines | not started |
| 12 | CHANGES: entry for the Last-Modified GMT fix (commit fd2d1501 shipped in 1.37.0 with no entry) | 6–10 lines | **worth adding retroactively to the 1.37.0 section** |
| 13 | php: re-test + guard the `pcntl_fork()` exit re-entry (child forked during an `exit()` returned into the request loop on 1.36.0, no guard at 872bf041) | 10–30 lines + test | not started |
| 14 | runtime: accept `--log -` for stderr in foreground mode | 10–20 lines | convenience only |
| 15 | docs: explain why the PHP SAPI is named "cli-server" (a rename would turn off OPcache on PHP 8.4 and older) | ~10 lines | documentation |
| 16 | **only if E3 fails** router: one app's failed start must not fail the whole reconfiguration | 200–600 lines (unknown) | not started |
| 17 | **only if E2 fails** application: load PHP modules linked against different libphp builds in one instance | unknown | not started |
| 18 | HTTP/2 — track only | — | 7 open PRs target 1.38; with aggregation off, Chromium opens ≤6 HTTP/1.1 connections per host, so test the PRs against Drupal admin pages |
| 19 | Native Windows — track only (companion freeunit-windows) | FreeUnit side: 10,000–18,500 new lines | see `engineering/windows-port-ci.md` |
| 20 | PHP worker mode — track only | — | issue #596 (1.38.0). When tagged: add a per-project `worker` switch (default off), test Drupal 11.4 and 12 (cron, settings changes, memory over 1,000 requests, Xdebug) **before** the tool offers it, and extend the D18 parity claim only after that test |

Bug fixes 1/2/9/11/12/13 belong to the bug-fix tracking issue **#597** (item 1 sits in wave 0 via #595); worker mode and schedules to the 1.38.0 tracking issue **#596**.

Also asked of other projects: `freeunitorg/docs` (extend `howto/drupal.rst`: uploads with `max_body_size`, TLS, `forwarded`, `trusted_host_patterns`, private/temporary dirs; drop `core/authorize.php` for Drupal 12), drupal.org (12.0.0-beta1 notes say PostgreSQL 19 while the code requires 18), Drupal CMS (a neutral variable marking a managed local environment).

## Milestones and capacity

| ID | Deliverable | Dates (targets) | Size |
|---|---|---|---|
| M0 | Phase 0 experiments | 2026-10-08 → 2026-10-30 | 23–29 person-days |
| M1 | Runtime build pipeline | 2026-11-02 → 2026-12-04 | 800–1,500 lines CI/shell |
| M2 | Linux core (alpha) | 2026-11-02 → 2026-12-18 | 4,000–6,500 lines Go |
| M3 | Databases, mail, cron, data commands | 2026-12-07 → 2027-01-22 | 2,000–3,500 lines |
| M4 | TLS, names, ports | 2026-12-07 → 2027-01-15 | 1,500–2,500 new + 1,689 reused |
| M5 | DDEV live import | 2027-01-04 → 2027-02-12 | 2,000–3,500 lines |
| **M6** | **macOS arm64** | **from the 1.37.1 tag**; target 2027-02-26 | 500–1,500 lines + CI |
| M7 | Developer workflow | 2027-01-18 → 2027-02-26 | 1,500–2,500 lines |
| M8 | Public beta | 2027-03-01 → 2027-03-19 | docs |
| M9/M10 | More services / 1.0 | 2027-04+ / target 2027-10-15 | 2,000–4,000 lines |
| M11 | Native Windows | no date | tool 2,000–4,000 lines; FreeUnit side from the windows plan |
| T1 | DDEV add-on that runs FreeUnit (optional) | after E17 | 1–2 person-weeks |

**Capacity check (the load-bearing number):** M1–M8 = **26–42 person-weeks and 11,500–20,000 lines of Go**; two people full time between 2026-11-02 and 2027-03-19 have **35–39 person-weeks** after holidays. The beta date holds only if the work lands in the lower half of the range; otherwise the beta moves before DrupalCon Edinburgh (2027-10-25) and 1.0 to 2028. Sizes are baselined on Symfony CLI (23,066 lines Go), DDEV (54,768), mkcert (1,381).

## Phase 0 experiments

E1 static-php-cli shared libphp module · E2 two PHP minors in one unitd · E3 one broken project vs shared reconfiguration (**E1–E3 blocking, decide the go**) · E4 routes-only change keeps OPcache warm · E5 Xdebug activation path (depends on FreeUnit ask 3) · E6 macOS non-root binds and LAN exposure · E7 `PHP_BINARY`/Package Manager under FreeUnit · E8 DDEV snapshot restore into native MariaDB · E9 where `*.localhost` resolves · E10 certificates and trust · E11 DDEV import corpus · E12 resource/start-time baseline vs DDEV · E13 SQLite concurrency · E14 BigPipe streaming and large uploads · E15 macOS binary distribution · E16 per-project PHP error log in foreground mode (depends on ask 4) · E17 route template across Drupal majors and file systems.

## CI design (plan §8.4)

- Docs: markdown lint + a check rejecting dash punctuation, home-directory paths and a private-host-name list; weekly link check.
- Go: `gofmt`, `go vet`, `staticcheck`, unit tests with `-race` on linux-amd64.
- End to end: Ubuntu 24.04 x86_64 **and arm64**, plus a macOS arm64 runner from M6; matrix over Drupal 10.6/11.4/12.0 × SQLite/MariaDB 11.8/MySQL 8.4 × the PHP versions of D7; every run includes the E17 probe suite and a check that `clean --all` leaves nothing behind.
- Runtime pipeline (M1): builds on a tag + a nightly check for new PHP patch releases (the project must patch its bundled runtimes within days of a PHP security release — risk R12).
- Corpus (M5): weekly run over 50 repositories, **publishes the pass rate**.
- Release: goreleaser, `SHA256SUMS`, cosign signatures, notarization from M6.

## Risks worth naming

- **R2 is the project's spine:** one or two maintainers; Symfony CLI and others stalled when their maintainer left, and DDEV runs on two paid maintainers (USD 114,757 income in 2025). Funding model is open decision 4.
- Bundled PHP falls behind security releases → patch-within-days obligation.
- Claim discipline: D18 governs positioning; the parity claim must not be extended to worker mode before it is tested.

## Open decisions for the maintainer

Name (Drupal trademark check, decide before M8) · organisation (freeunitorg recommended, before M2) · licence (Apache-2.0 stated) · **funding model** (before M8, metric S6 needs paid/committed time) · relationship to the findings repo `andypost/freeunit-drupal` · contact with the Drupal CMS Launcher maintainers · whether to pursue a drupal.org Official Docs listing after the beta (DDEV took six years) · whether to build T1 and talk to DDEV · **the two named people for Phase 0 (target 2026-10-08)**.

## Related

- `strategy/freeunit-windows-and-4drupal-repos.md` — both new repos, gates and the coupling
- `engineering/windows-port-ci.md` — the companion port's CI design
- `releases/1.37.1-plan.md` — ask 1: the release that unblocks M6
