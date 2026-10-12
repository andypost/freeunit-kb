---
title: "FreeUnit v1.35.6 Release"
description: "Pre-release status, blockers and release plan"
tags: [freeunit, v1, release, 1.35.6]
milestone: "1.35.6"
due: "2026-07-16"
status: "pre-release (~85%)"
---

# FreeUnit 1.35.6 Release

**Branch:** `pre-1.35.6` (commit `19fe644`)
**Version:** 1.35.6 (NXT_VERSION)
**Deadline:** July 16, 2026

## What's included

### Security audit (14 vectors) [OK]
- cgroup: `cgroup.procs` path append protection (#119)
- WebSocket: OOB / cross-frame disclosure
- IPC: SCM_CREDENTIALS sender auth
- TLS: write-path half-close (PR #54)
- Config: NUL/empty C-string values (#114)
- Mount: openat2 validation (#115)
- Content-Length: duplicate/overflow (#113)
- libunit: bounds on request fields + Java InputStream (#112)

### Graceful shutdown [OK]
- SIGQUIT graceful stop (workers drain before exit)
- SIGTERM — fast exit
- Listener drain (two-phase)
- Engine: symmetric idle/active connection tracking

### Other [OK]
- OpenTelemetry 0.24 to 0.32 (semconv, HTTP+gRPC)
- wasmtime 35 to 36 (CVE fixes)
- New C tests (cgroup, conf_parse, port_fail, string)

## Blockers (3 open issues)

- https://github.com/freeunitorg/freeunit/milestone/1

## Release plan

1. Close 3 issues
2. Merge `pre-1.35.6` to `master` (--no-ff)
3. Tag v1.35.6
4. Publish GHSAs (GHSA-768w, GHSA-g6v8)
5. Backport to 1.34.x LTS
6. Docker images on GHCR
