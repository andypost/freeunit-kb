# FreeUnit Project History

## Original NGINX Unit (2017-2025)

| Date | Event |
|------|-------|
| Jan 2017 | Initial commit by Igor Sysoev (NGINX Inc.) |
| 2017–2019 | Active development: 7 languages, isolation, live config |
| Mar 2019 | F5 acquires NGINX for $670M |
| 2019–2022 | Slower development. HTTP/2, QUIC, Service Mesh planned — never shipped |
| 2022 | Founders leave F5. Moscow office closes. Angie fork created (NGINX, not Unit) |
| Apr 2025 | F5 announces Unit moves to "critical maintenance only" |
| Oct 2025 | NGINX Unit repo archived |

## FreeUnit Revival (late 2025 – present)

**Revival by Евгений Фрост (TuzelKO).** Started late 2024 / early 2025.

### Pre-release work
| Date | What |
|------|------|
| Sep 2024 | Release process documented |
| Oct 2025 | Python 3.14 Docker images, init-1.35 branch |
| Late 2025 | Infrastructure: CI, Docker, GHCR, .deb packages rebuilt |

### Releases (6 in 3.5 months)

| Version | Date | What |
|---------|------|------|
| **FreeUnit 1.35.1** | Apr 3, 2026 | First release. Project revived. Community fork announced. |
| **1.35.2** | Apr 4, 2026 | Next day. Rapid iteration. |
| **1.35.3** | Apr 7, 2026 | |
| **1.35.4** | Apr 30, 2026 | |
| **1.35.5** | May 29, 2026 | Stable. Milestone closed. |
| **1.36.0** | Jul 17, 2026 | Security hardening release. 38+ fixes. Graceful shutdown. OTel 0.32. |

### Key numbers
- **236 commits** from revival to 1.36.0
- **~140 open PRs merged** (from issue #139 being the merge of pre-1.35.6)
- **Docker images:** PHP 8.3/8.4/8.5, Python 3.13/3.14, multi-arch (amd64 + arm64)
- **.deb packages:** Debian Trixie, with SHA256SUMS verification

### Community
| Metric | | |
|--------|-|-|
| **Team** | Alexander (founder), Andrey (maintainer), 5+ contributors |
| **GitHub org** | freeunitorg |
| **License** | Apache 2.0 (unchanged from upstream) |
| **Release model** | Security ≤7 days, minor every 8-12 weeks, LTS 2 years |

**Early community interest (pre-revival):** 2023-06-09 — Pavel Zavadski
(GitHub `Pavlusha311245`; Telegram `@Pavlusha2Sniper`) publishes a Habr tutorial
about NGINX Unit ("Простым языком о простом NGINX UNIT", ~22K readers). He later
becomes a **FreeUnit contributor**. The tutorial documents the pre-fork architecture
(JSON config, REST API, /status, language modules, TLS via /certificates) — a useful
"before" baseline for the "what FreeUnit added" narrative.

**Timeline note (2026-08-31, verified):** the Habr author Pavel Zavadski is the
same person now contributing to FreeUnit — Telegram `@Pavlusha2Sniper`, GitHub
`Pavlusha311245`. (Two handles, one person; not two accounts.)

### What sets FreeUnit apart from upstream Unit
- Active development (upstream archived)
- Security hardening (14 audit vectors, 2 GHSA advisories)
- OpenTelemetry 0.24→0.32 with gRPC
- Graceful shutdown (SIGQUIT)
- njs 1.0.0
- wasmtime 36 (CVE fixes)
- TrueAsync experimentation
- Alternative-dispatch protocol research
- Roadmap: P4 persistent workers, prototype+fork shared opcache, body streaming

### Adjacent project (same founder)
| Project | Status |
|---------|--------|
| **freeunit2** | PoC: Rust orchestrator + NTS PHP workers. Complete. |

### Digest webhook secret handling (2026-09-03)
| Variant | Result | Expectation |
|---------|--------|-------------|
| Hardcoded HMAC secret in digest prompt | Removed: leaked into every run output | Never store secrets in prompts |
| Job-scoped notepad KV | Adopted: set/get roundtrip ok, HMAC builds from it, prompt holds reference only | Agent reads secret at runtime, never prints/logs it |
| Host env var | Pending: only admin edits env | Operator sets it, prompt references $NAME |
| External manager (Bitwarden/1Password) | Rejected as heavy for one secret | Revisit if secret count grows |
| Delivery to receiver | 404 unknown route / 401 bad signature (receiver rotated secret) | Delivery stays down until receiver re-pins route + secret; digest relies on local output channel |
