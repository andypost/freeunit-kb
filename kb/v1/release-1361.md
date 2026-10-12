# FreeUnit 1.36.1 — Release

**Released:** 2026-08-29 · **Tag:** `1.36.1` + `unitctl/1.36.1` · **Branch:** master

## Build status

| Artifact | Result |
|----------|--------|
| Docker images | ✅ success — 75 jobs (build+merge, amd64 + arm64) |
| Debian packages | ✅ success — build-trixie, package-qa, smoke-test (php 8.3/8.4/8.5, py 3.13) |
| unitctl | ✅ success (published first, 05:11 UTC) |
| GitHub release | ✅ LIVE, Latest (05:19 UTC) |
| Seccomp AF_ALG | ✅ success |

## What changed (highlights)

- **Graceful shutdown** (SIGQUIT + listener drain + active tracking) — #107/#108/#111. User-facing feature.
- **OTel** 0.24 → 0.32 (major bump, semconv changes); span export outcome counters; flush pipeline before router exit.
- **njs 1.0** — first stable release.
- **OpenSSL 4.0** compatibility (reason-code names, non-deprecated cert APIs, EVP_MAC ticket callback) — #213.
- **/status counters declared 64-bit** (int64) in OpenAPI — fixes unitctl deserialization >2^31 — #247.

## Security

- **wasm** bindgen 0.68.1 → 0.72 (clang-22 fix; opaque placeholder structs) — #250.
- **port** authenticate PROCESS_READY by kernel pid (SCM_CREDENTIALS / SCM_CREDS) — #253. PR1 of #231.
- **router** release start slot on early failure — #236.
- **dependabot** target default branch (not pre-1.35.6) — #242; security updates now fire.
- setup-java 5 → 6 — #244.

## Post-release start-fail hardening (part of #231 series)

- #255 — router: clear proto_port_requests when a prototype start fails (wedge) — 2026-08-30.
- #254 — capability: keep running when capget() is filtered (A4/P0).
- #259 — test: provision tzdata in isolation rootfs (fixes #256).
- #263 — port: fail the start when worker queue cannot be mapped.

## Full release-cadence notes

- Release philosophy: predictable cadence, stability over numbers. patch = security/critical, minor = feature/hardening (8-12 wk), major = breaking.
- Since 1.36, releases ship from master directly (no pre-1.36 branch, no 1.36 milestone).
