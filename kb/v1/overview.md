---
title: "FreeUnit v1 Overview"
description: "Community LTS fork of NGINX Unit application server"
tags: [freeunit, v1, lts, nginx-unit, fork]
resources:
  - "https://github.com/freeunitorg/freeunit"
  - "https://github.com/andypost/unit"
---

# FreeUnit v1 Overview

**FreeUnit** — Community LTS fork of the original NGINX Unit (archived October 2025).

## Origin

- **March 2019:** F5 Networks acquired Nginx Inc. for $670M. Founders Igor Sysoev
  and Maxim Konovalov joined F5 to continue development.
- **2022–2024:** After the acquisition and geopolitical events of 2022, key Russian
  developers (including the founders) left F5. A separate fork, Angie (Nginx,
  not Unit), was created by the departing team.
- **April 2025:** F5 maintainers announced NGINX Unit moved to "critical
  maintenance only" — no new features, only security and critical bug fixes.
- **October 2025:** Upstream NGINX Unit repository archived.
- **FreeUnit** — community-driven continuation with full feature development,
  security hardening, and language runtime updates.

## What the original Unit never shipped (F5 abandoned)

| Feature | Planned | FreeUnit status |
|---------|---------|-----------------|
| HTTP/3 (QUIC) | Experimental | Deferred — H2/H3 better served at the edge |
| Built-in message queue broker | Blueprint | Not planned (out of scope) |
| Service Mesh / Sidecar (mTLS, discovery) | Blueprint | Not planned (out of scope) |
| WASM at the core (serverless) | Basic only | wasmtime 36 (security maintenance) |
| Dynamic isolation changes via API | Limited | Isolation block in config (reload-based) |
| Script routing (JavaScript/Lua) | Planned | **Shipped** — njs 1.0.0 in 1.36.0 |
| HTTP/2 | Planned | Roadmap D2 (~3 months) |

## Key facts

- **Repository:** github.com/freeunitorg/freeunit
- **Personal fork (roadmap/drafts):** github.com/andypost/unit (branch `roadmap`)
- **Maintainer:** Andrey Postnikov (andypost)
- **License:** Apache-2.0
- **Status:** Active
- **Release model:** Security releases ≤7 days, minor every 8-12 weeks, LTS 2 years

## Supported languages

PHP 8.3/8.4/8.5, Python 3.8–3.14, Node.js 20/22/24, Go 1.25/1.26, Ruby 3.3/3.4, Perl 5.38/5.40/5.42, Java 17/21, WebAssembly (wasmtime)

## Docker images

GHCR: `ghcr.io/freeunitorg/freeunit:latest-{php8.5, python3.14, minimal, ...}`

## Philosophy

"Free as in freedom." In lineage: freenginx · MariaDB · LibreOffice · OpenSSH.
