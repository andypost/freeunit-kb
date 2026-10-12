# Dependency & CI hygiene — verified inventory (2026-09-16; CI state re-verified 2026-10-09)

Verified against `origin/master` `df9843b0` (2026-09-15) for the 2026-09-16 inventory,
and re-verified against `origin/master` `0f1ec0b1` (2026-10-09) for the CI items below.
A local checkout is often behind — re-verify (`git fetch`, `git ls-tree
origin/master .github/workflows/`) before reusing any line below.

## Build & pinning

- Build system: `configure` (193 lines) + `auto/**` shell; the Makefile is
  GENERATED (no `Makefile` and no `CMakeLists.txt` in the tree). CMake appears
  only inside tooling (node-gyp in the clang-ast job).
- Bundled contribs are pinned per component: `pkg/contrib/src/{wasmtime,njs,
  wasi-sysroot,libunit-wasm}/version` + `SHA512SUMS`; source tarballs come from
  packages.freeunit.org checksum-verified. Bumps are ordinary PRs (njs
  1.0.0 → 1.0.1, #387).
- `pkg/eol.json` is the single source of truth: runtime/OS EOL with grace policy
  (12 months runtimes / 36 months OS) PLUS a `dependencies` section documenting
  floor / floor_declared_by / tested_ceiling / source for openssl, tomcat, jetty,
  ecj, classgraph, wasmtime_c_api, wasmtime_crate. Read by `pkg/eol` and gated by
  `eol-check.yml`.
- Compiler: `-Wall -Wextra -Werror` (auto/cc); `make E=0` disables.

## CI gates on master (`.github/workflows/`)

| Workflow | What it gates |
|---|---|
| `audit.yml` | `cargo audit --deny warnings` over EVERY tracked `Cargo.lock` (list discovered via `git ls-files '*Cargo.lock'`, one matrix leg per lock) — PR on lock/toml change, push to master, weekly cron. Landed #399 (2026-09-15). |
| `analysis-clang-ast.yml` | Custom clang plugin (`freeunitorg/clang-ast`, branch `unit`) AST checks, then builds and RUNS the C unit-test suite (`./build/tests`), then every language module + wasmtime pinned from pkg/contrib. |
| `sanitize.yml` | ASan+UBSan matrix (python / php / go) over a named test subset, with `check-sanitizer-reports.sh` + `sanitizer-allowlist.txt` as the actual gate. `detect_leaks=0` is a documented follow-up; the go leg is experimental. |
| `fuzzing.yml` | In-tree libFuzzer targets; PR trigger on `src/nxt_http*`, `src/nxt_h1proto*`, `src/nxt_conf*`, `src/nxt_utf8*`, `src/nxt_controller*`, `configure`, `auto/**`, `fuzzing/**`. Supersedes the old OSS-Fuzz cifuzz workflow (gone from master). |
| `security-seccomp.yml` | AF_ALG seccomp mitigation vs the shipped Docker profile. |
| `security-syscalls.yml` | Syscall-drift baseline (advisory until a baseline is committed). |
| `lint-whitespace.yml` | `git log --check` over the PR series; extended to run on pushes to master in the 1.37.1 cycle. |
| `build-test.yml`, `build-distros.yml`, `build-deb.yml` | Runtime/OS matrices, distro legs, packaging. |
| `unitctl.yml`, `eol-check.yml` | unitctl build+test (incl. musl / TLS-free leg) and the EOL policy check. Also on master: `build-test-macos.yml` (builds and runs the C tests on macOS) and `rust-version.yml` (builds every crate with its declared rust-version). |

## Style tooling

- `.editorconfig` + `.rustfmt.toml` (Rust only). NO `.clang-format`,
  `.clang-tidy` or cppcheck config anywhere in the tree, and no style target in
  the generated Makefile: C style is enforced by review, compiler warnings and
  clang-ast.
- A whole-tree `clang-format` over ~133k lines of C would reformat against
  several open PRs; only a changed-lines-only gate is cheap.

## Linkage / module boundaries

- C core (`unitd`) + loadable per-runtime language modules (.so) + `libunit.a`
  linked into application processes (`NXT_LIB_UNIT_STATIC`, shipped by
  `libunit-install`). The Go binding includes only public `nxt_unit*.h`.
- `tools/unitctl` is Rust in its own cargo workspace (`unitctl`,
  `unit-client-rs`, `unit-openapi`), driving the control API over HTTP through
  the OpenAPI spec: zero link-time coupling to the C core, `Cargo.lock`
  committed, TLS behind a Cargo feature (#359).

## Open items (verified live 2026-10-09, master `0f1ec0b1`)

Closed since the 2026-09-16 inventory:

- **#400** (contrib wasmtime pin four majors behind, "audited by nothing") —
  CLOSED 2026-09-20 as completed; the contrib pin is **48.0.5** since 1.37.0.
- **PR #99** (Trivy filesystem vulnerability audit) — CLOSED 2026-10-04
  **without merge** (draft): the recorded decision is "no Trivy".
- **dependabot** now covers `github-actions` **and `cargo`** — eight cargo
  directories (tools/unitctl, src/otel, src/wasm-wasi-component, pkg/eol, four
  test fixtures), weekly, grouped (otel crates together, minor-and-patch as one
  group), `open-pull-requests-limit: 3`. Landed #565 and #570.
- **`pkg/eol.json` OpenSSL ACTION** — done: `tested_ceiling` is now **3.5.9**
  (LTS, supported to 2030-04-08) plus **4.0.3** built with
  `-DOPENSSL_NO_DEPRECATED`; 3.6.5 was dropped before its 2026-11-01 upstream
  EOL (#613).

Still open (CI):

- **#632** — no CI job compiles a **32-bit target**, so a 32-bit-only `-Werror`
  survived into the 1.37.0 release. The code fix is in the 1.37.1 cycle; the
  gate is still missing.
- **#308** — a leg wedged in the checkout post-step blocks every rerun on the PR.
- **#402** — the remaining Python-leg time is **sleeping tests**, not missing
  parallelism (PR #657 cuts the sleeps in three python-leg files and fixes the
  shard table, open).
- **#619** — a size option of 2^31 or more has no defined value on a 32-bit build
  (the conf counterpart of #632).
- **#654** — Tracking: the CI job shape, its cost and the rules that must survive a
  change (opened 2026-10-10, follows the PR-job reduction #643).
- **#655** — ast-grep gate: rule widening and precision follow-up from #449.
- **PR #617** (draft) — run unitd and serve a request on macOS;
  **PR #626** (draft) — reproducible builds, phase 1.
- **PR #471 / #479** (draft) — libFuzzer target for the HTTP/2 frontend, and
  h2spec + CI + docs (stages of the open h2 stack).
- Merged in the cycle (were open on 2026-10-09): **#449** ast-grep baseline +
  require-tests gates (now `lint-astgrep.yml` + `require-tests.yml`), **#450**
  (retitled/landed as `layout-check.yml` — shared-memory struct layout check),
  **#637**, **#642**, **#643**; **#624** closed by #641 ("make a stuck websocket
  test fail instead of hang").
- **Style-gate decision still open** — no `.clang-format`/`.clang-tidy`/cppcheck
  config in the tree and no recorded "no".

CI landed in the 1.37.1 cycle (since 1.37.0, all merged): whitespace lint on
master pushes; build and run the C tests on macOS; "every version site agrees
with the version file" check; Docker Rust pin agreement check; unitctl tag
created on the commit the release tag points to; otel crates kept out of the
dependabot minor-and-patch group; cargo dependabot; rust-version per crate with a
CI check; wasm-wasi-component leg fails when all its tests skip; weekly
Fedora/Alpine distro legs; apt and pytest steps bounded by time; gcc 16, clang 23
and the RHEL 8 floor in containers; OpenSSL 3.5 LTS in place of 3.6; seccomp run
once per PR push and on release tags; unitctl on master pushes only when its
paths change; mono and ccache steps removed; ubuntu-26.04 pinned; Fedora
hardening-strict leg asserts the compiler and OpenSSL versions.

## Verdict on "adopt Mimic's dependency hygiene" (2026-09-16 proposal)

- **Already done:** per-component pinned + checksummed contribs, `pkg/eol.json`
  as EOL/audit single source of truth, `cargo audit` over every lock,
  ASan+UBSan gate, libFuzzer PR gate, clang-ast AST gate,
  `-Wall -Wextra -Werror`, unitctl fully isolated from the C core.
- **Misapplied to this stack:** pinning "in Makefile/CMakeLists" (build is
  `configure` + `auto/`), "unitctl must not include deep internal headers / must
  link minimal shared libraries" (unitctl is Rust, no C linkage at all),
  valgrind/cppcheck/scan-build (already covered by the sanitizer gate + the
  clang-ast plugin), "avoid static linking of large components" (libunit.a is
  static by design for app processes).
- **Real deltas (2026-10-09):** dependabot **gomod and docker** ecosystems (cargo
  and github-actions are covered now); the **32-bit compile gate** (#632) and the
  **s390x hang** (#624); a **style-gate decision** (changed-lines clang-format or
  a recorded "no"). Closed since the proposal: the unaudited contrib tarball
  (#400) and the Trivy decision (PR #99).
