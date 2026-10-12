# Security Scanning: Who Is Responsible For What

## The Question

Does FreeUnit need to scan Go/Rust/PHP dependencies for CVEs, or is that
the distribution's job?

**Answer:** Both — but the boundary matters.

---

## Layer Model

```
                    CVE Ownership
┌─────────────────────────────────────┐
│ User's PHP code / WordPress/Drupal  │ ← USER (not FreeUnit's problem)
├─────────────────────────────────────┤
│ PHP interpreter (libphp)            │ ← DISTRO (Debian security tracks PHP CVEs)
├─────────────────────────────────────┤
│ System libraries (OpenSSL, libc,     │ ← DISTRO (Debian security team)
│  PCRE2, libxml2, zlib, curl, etc.)  │
├─────────────────────────────────────┤
│ FreeUnit C core                      │ ← FREEUNIT (our code, our bugs)
├─────────────────────────────────────┤
│ Rust crates (OTel, unitctl, wasm,   │ ← FREEUNIT (we vendor/bundle them)
│  fake_upstream, fake_otlp, eol)     │
├─────────────────────────────────────┤
│ Bundled contribs (wasmtime, njs)     │ ← FREEUNIT (we ship the tarballs)
├─────────────────────────────────────┤
│ Docker base image (Debian Trixie)   │ ← FREEUNIT (we publish the image)
└─────────────────────────────────────┘
```

---

## What The Distribution Covers

When you `apt install freeunit` on Debian Trixie:

| Dependency | Who tracks CVEs | FreeUnit needs to do? |
|------------|----------------|----------------------|
| OpenSSL | Debian security | Nothing — apt upgrade pulls fix |
| PCRE2 | Debian security | Nothing |
| libxml2 | Debian security | Nothing |
| zlib | Debian security | Nothing |
| PHP (libphp-embed) | Debian security + sury.org | Nothing — php upgrade handles it |
| glibc | Debian security | Nothing |
| curl, libcurl | Debian security | Nothing |

**The distro handles everything in `apt install freeunit`.**

---

## What FreeUnit Must Cover

### 1. Bundled Rust crates (our Cargo.tomls)

We ship these binaries in our Docker images:
- `unitctl` (CLI tool)
- `fake_upstream`, `fake_otlp`, `eol` (testing tools, not in production)
- `wasm-wasi-component` (WASM runtime)

These are compiled FROM source during `./configure --otel` build. The distro
does NOT ship them (they're not in Debian repos). **FreeUnit is responsible.**

**Solution:** `cargo audit` in CI. Simple, one command:
```yaml
- name: cargo audit
  run: cargo install cargo-audit && cargo audit
  working-directory: src/otel
```

Runs against the Rust Advisory Database (RUSTSEC) — same as GitHub dependabot
would do for Cargo.toml.

### 2. Bundled contrib tarballs (wasmtime, njs)

We download these as tarballs and ship in Docker images:
```
https://packages.freeunit.org/wasmtime-36.0.12.tar.gz
https://packages.freeunit.org/njs-1.0.0.tar.gz
```

No package manager tracks their CVEs. **FreeUnit is responsible.**

**Solution:** Manual tracking (what we do now — we know when wasmtime CVE drops
and bump to 36.0.12). Could be automated with a weekly cron that checks:
- `gh release view wasmtime/wasmtime --json body` and greps for "security"
- Or subscribes to their security advisories

### 3. Docker images (we publish)

Our GHCR images bundle all of the above. A CVE in wasmtime or a Rust crate
means our Docker image is vulnerable until we rebuild.

**Solution:** `trivy` or `docker scout` scan on release:
```bash
trivy image ghcr.io/freeunitorg/freeunit:latest-php-8.5
```

This catches everything — system libraries AND our bundled code.

---

## What The User Covers

- PHP code vulnerabilities (SQLi, XSS, RCE in their app) — not FreeUnit's problem
- WordPress/Drupal plugin CVEs — user updates plugins
- config mistakes (exposed control socket, weak isolation) — FreeUnit can warn but can't enforce

---

## Three-Tier Recommendation

### Tier 1: CI gate (every PR, free)

```yaml
# Add to dependabot.yml
updates:
  - package-ecosystem: cargo
    directory: "/src/otel"
    schedule:
      interval: weekly
  - package-ecosystem: cargo
    directory: "/tools/unitctl"
    schedule:
      interval: weekly
  - package-ecosystem: gomod
    directory: "/go"
    schedule:
      interval: weekly
  - package-ecosystem: docker
    directory: "/pkg/docker"
    schedule:
      interval: weekly
```

GitHub does this for free. No tokens, no infra. Opens PRs automatically when
a dependency has a known CVE.

Also add to CI:
```yaml
- uses: rustsec/audit-check@v2
  with:
    token: ${{ secrets.GITHUB_TOKEN }}
```

### Tier 2: Release gate (every release, automated)

```bash
# Before tagging:
trivy image ghcr.io/freeunitorg/freeunit:latest-php-8.5
cargo audit
# If critical CVE → block release
```

### Tier 3: Proactive monitoring (weekly, my job)

I can run a weekly cron that:
1. Checks `cargo audit` on all Cargo.tomls
2. Checks wasmtime releases for security advisories
3. Checks njs releases for security fixes
4. Reports: "OK" or "UPDATE NEEDED: wasmtime 36.0.x -> 37.0.0 (CVE-XXXX)"

---

## What Actually Matters For FreeUnit

| Threat | Likelihood | Impact | FreeUnit action |
|--------|-----------|--------|----------------|
| CVE in OpenSSL (system) | High | Critical | Nothing — distro patches |
| CVE in tokio (Rust crate) | Low | High | `cargo audit` catches it |
| CVE in wasmtime (contrib) | Low | Critical (sandbox escape) | Manual monitor (1.36.0 already updated) |
| CVE in PHP interpreter | Medium | High | sury.org patches, we rebuild Docker |
| CVE in FreeUnit C code | Low | Critical | We fix it — security audit proved we can |

**Biggest gap today:** No `cargo audit` in CI. Rust crates (OTel, unitctl)
could have a known RUSTSEC and we'd never know until someone notices.

**Second gap:** No Docker image scanning. We publish images with bundled
wasmtime/njs — if a wasmtime CVE drops between releases, our images are
vulnerable and nobody scans them.

**Both are cheap to fix.** Dependabot for Cargo + Go is zero-config.
Trivy scan is one CI step.

---

## 2026-09-16 Update — which of these gaps have since closed

Verified on `origin/master` `df9843b0` (2026-09-15). Full inventory:
`engineering/dependency-ci-hygiene.md`.

- **CLOSED (cargo audit).** `.github/workflows/audit.yml` (PR #399, merged
  2026-09-15) audits EVERY tracked `Cargo.lock` with
  `cargo audit --deny warnings`, one matrix leg per lock, on lock/toml change,
  push to master and a weekly cron. The "Biggest gap today: No `cargo audit` in
  CI" claim above is historical — the Rust crates named in the layer model are
  now covered.
- **CLOSED (fuzzing shape).** The OSS-Fuzz cifuzz workflow is gone from master;
  `fuzzing.yml` now runs in-tree libFuzzer targets as a PR gate on the HTTP
  parser / config / UTF-8 / controller paths. Two new gates also exist:
  `security-syscalls.yml` (syscall drift) and `eol-check.yml` (EOL policy from
  `pkg/eol.json`).
- **PARTLY CLOSED (bundled contribs).** `pkg/eol.json` now documents each
  dependency's floor, declared-by, tested ceiling and source, including both
  wasmtime pins. The C-API pin (43.0.1) is still "audited by nothing" and is hit
  by RUSTSEC-2026-0269 / RUSTSEC-2026-0222 — open as freeunit#400.
- **STILL OPEN.** dependabot covers `github-actions` only (the cargo / gomod /
  docker block in Tier 1 above is still unapplied); PR #99 (Trivy filesystem
  audit) has been open since 2026-07-07 with no decision, so the Docker-image
  scan in Tier 2 is still manual.
