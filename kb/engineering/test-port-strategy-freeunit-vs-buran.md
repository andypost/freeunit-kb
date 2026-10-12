---
title: Test-port strategy — FreeUnit #406 vs Buran
description: Why FreeUnit's suite needs a port-remap layer (PR #406) to run in parallel, and how Buran avoids the whole problem by binding an ephemeral port (127.0.0.1:0).
tags: [testing, ports, ci, parallelism, buran]
status: qa
updated: 2026-09-27
resources:
  - https://github.com/freeunitorg/freeunit/pull/406
---

# Test-port strategy — FreeUnit #406 vs Buran

Someone asked @TuzelKO how Buran handles the port for tests, pointing at FreeUnit
PR **#406** as *"криво, но позволяет параллельно запускать"*. This is what that is
about.

## The problem in FreeUnit

The suite names listeners **literally everywhere** — **235 `*:PORT` literals in 73
files** — and the capability probes (`test/unit/check/chroot.py`,
`test/unit/check/isolation.py`) **wildcard-bind `*:8080` at session startup, before
any test is selected**. So one fixed band means **one pytest process per network
namespace**: a second run (another agent, a second worktree, an xdist worker) dies
at startup with `bind("0.0.0.0:8080") failed`.

Workarounds today, both hacky:

- the local harness **serializes with a lock** (no parallel runs);
- `tools/unit-build` **fakes a shift by sed-rewriting a copy** of the suite —
  including a special expression for `8080-8090`, because a bare `s/8080/$PORT/`
  turns that *range* descending and Unit rejects it.

## What #406 does

Translate the port **where it is resolved**, not at 235 call sites.
`HTTP1.http()` and `Control._get_args()` are the only two places a port becomes a
`connect()` or reaches unitd, so `test/unit/port.py` maps the historical literals
onto a session band and `--port N` / `UNIT_TEST_PORT` moves the whole suite.

- **One-shift map:** `literal + base − 8080` → **identity at base 8080** (an
  unmodified run is unchanged, so CI stays safe). Bases `7876..32404` accepted.
- **Only `/config`** requests are remapped (URL + body); `/certificates` and
  `/js_modules` take opaque payloads.
- **`port_lint.py`** scans the test sources with `ast` and fails CI on a *new* raw
  literal that bypasses the map — the PR's recurring failure mode.
- **Off-base CI leg:** `build-test.yml` re-runs the whole `test` tree with
  `UNIT_TEST_PORT=18080` on one leg.

## Why it's "hacky" — and why FreeUnit can't just do what Buran does

**Buran's tests bind `127.0.0.1:0`** (`crates/buran-router/src/http1.rs:1640`) —
the kernel picks an ephemeral port, and the test reads it back via
`local_addr().port()` and hands it to the client. **No fixed band → no collision →
parallel is trivial.** Config-parse tests mention `*:8080` only as *strings*; they
never bind.

> **Not a design decision.** @TuzelKO is right that this fell out by accident: `bind
> ":0"` + `local_addr()` is the **Rust/tokio idiom**, so parallel-safety arrives for
> free without anyone thinking about it. It *holds* because Buran's tests are
> **in-process** (bind a loopback pair, drive the code) — the port is a local
> detail, never a config or an assertion. The whole repo has just two socket binds:
> the real listener from config (`lib.rs:265`) and the test pair (`http1.rs:1640`).

FreeUnit cannot do that, because in the suite the port is not merely a bind — it is
also a **config value and an assertion value**: the listener `"*:8080"`, proxy
targets that must name another listener, helper-upstream ports, and `Server-Port` /
`Location` expectations. A port you bind as `:0` can't be written into a config
beforehand or asserted against. So FreeUnit must **know the port up front**, which
forces a remap band + lint rather than `:0`.

## Still blocks full parallelism (even after #406)

- the namespace-global abstract socket `@sock` (`test_unix_abstract.py`);
- `test_asgi_lifespan.py` writes into the checkout;
- the Go helper's `GOPATH` under `build/go`;
- `test/go` and `test/node` fixtures hardcode 8080 in their own sources → unsafe off
  the default base.

**Takeaway:** Buran sidesteps the class by *not naming* the port (bind `:0`); FreeUnit
must *name* it (config + assertions), so it fixes the class by remapping at the two
resolve points and guarding the map with a lint.
