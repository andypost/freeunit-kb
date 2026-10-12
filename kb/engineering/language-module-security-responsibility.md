# Language Module Security — Who Is Responsible

FreeUnit supports 8 language runtimes. Each has a different security model.

---

## Quick Summary Table

| Language | Runtime source | CVE tracking | FreeUnit action needed? |
|----------|---------------|-------------|------------------------|
| **PHP** | Distro (sury.org) + Docker | sury.org, Debian | Nothing — distro patches |
| **Python** | Distro (Debian) | Debian security | Nothing — distro patches |
| **Node.js** | Distro or NodeSource | Node.js LTS team (Debian tracks LTS) | Nothing — distro patches |
| **Go** | Distro (Debian) | Debian security | Nothing — distro patches |
| **Ruby** | Distro (Debian) | Debian security | Nothing — distro patches |
| **Perl** | Distro (Debian) | Debian security | Nothing — distro patches |
| **Java** | Eclipse Temurin | Adoptium project | **We bundle it in Docker** — partial responsibility |
| **WASM (wasmtime)** | Bundled tarball | **We track it** (wasmtime releases) | **Full responsibility** |

---

## PHP

FreeUnit links against `libphp8.X-embed` — system package from Debian or sury.org.

- PHP CVEs → sury.org or Debian patches
- FreeUnit Docker images use `apt install libphp8.4-embed libphp8.5-embed`
- `apt upgrade` pulls the fix
- No FreeUnit action needed

## Python

FreeUnit uses CPython via distro package.

- Python CVEs → Debian security
- FreeUnit Docker: `apt install python3.13 python3.13-dev`
- No FreeUnit action needed

## Node.js

FreeUnit links against libnode from distro or NodeSource.

- Node CVEs → Node.js LTS team, then NodeSource, then Debian
- FreeUnit Docker: `apt install nodejs`
- No FreeUnit action needed

## Go

FreeUnit uses Go for the Go language module (tests, not daemon).

- Go CVEs → Debian security
- No FreeUnit action needed

## Ruby

FreeUnit links against libruby from distro.

- Ruby CVEs → Debian security
- No FreeUnit action needed

## Perl

FreeUnit links against libperl from distro.

- Perl CVEs → Debian security
- No FreeUnit action needed

## Java

Java is different — FreeUnit Docker images bundle a specific JDK build
(Eclipse Temurin from Adoptium). The JDK is pre-installed in the Docker image.

- Java CVEs → Adoptium project
- FreeUnit Docker: `FROM eclipse-temurin:17-jdk` or `21-jdk`
- **Partial responsibility:** if a Java CVE drops, we need to rebuild our Docker
  images to pick up the new temurin base image
- GitHub Dependabot already tracks Docker base image updates if configured

## WASM (wasmtime)

We download wasmtime source tarballs and compile into the FreeUnit binary.

- wasmtime CVEs → **we track them manually**
- Currently: wasmtime 35→36.0.12 in 1.36.0 (sandbox-escape CVE fix)
- **Full responsibility**

---

## What FreeUnit Actually Ships (that we control)

```
In the FreeUnit binary (our code):
├── C core (nxt_*.c) — our code, our bugs
├── OTel Rust crate — we compile it, `cargo audit` needed
├── unitctl (Rust CLI) — we compile it, `cargo audit` needed
├── fake_upstream, fake_otlp, eol (Rust tools) — we compile them
└── wasmtime (C/Rust) — we compile it, manual CVE tracking needed

In the Docker image (inherited from Debian):
├── PHP 8.x — distro handles
├── Python 3.x — distro handles
├── Node.js 20/22/24 — distro handles
├── Go 1.25/1.26 — distro handles
├── Ruby 3.3/3.4 — distro handles
├── Perl 5.38/5.40/5.42 — distro handles
└── Java 17/21 (Temurin) — Adoptium handles, but we pick up via Docker base image
```

---

## Conclusion

| Responsibility | Who | What |
|---------------|-----|------|
| Language runtimes (PHP, Python, Node, Go, Ruby, Perl) | **Debian / distro** | `apt upgrade` handles CVEs |
| Java JDK | **Adoptium** via Docker base image rebuild | Rebuild Docker when temurin updates |
| Rust crates (OTel, unitctl) | **FreeUnit** | `cargo audit` in CI — cheap, add it |
| wasmtime | **FreeUnit** | Manual CVE tracking — already doing it |
| FreeUnit C code | **FreeUnit** | Security audit + our fixes |

**The only practical gap was `cargo audit`.** All language runtimes are handled
by the distro. Adding dependabot for Cargo + Go is five lines of YAML,
and a `cargo audit` step is another ten lines. Everything else is already working.
