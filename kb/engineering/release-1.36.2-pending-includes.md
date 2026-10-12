---
title: Forthcoming release — what from the #500+ wave belongs in it
description: Triage of open PRs #508/#515–#523 and issue #516 against the pending release. Security/DoS fixes are patch-worthy (per the semver rule); bugs, leaks and perf go to the next patch/minor. Draft status noted (only #508/#515/#523 are ready).
tags: [release, triage, security, dos, semver]
status: triage
updated: 2026-09-27
---

# Pending release — what from #500+ belongs in it

> **OUTCOME (2026-10-04): the wave shipped as MINOR 1.37.0** (tag `1.37.0`, published
> 2026-10-04T18:10:44Z) — not as the patch 1.36.2 this triage planned. Its 116-entry
> section carries 8 Feature and 32 Change entries, which is exactly why it could not be a
> patch. Read the triage below as history; the current release-description findings live in
> `release-1.37.0-description-check`.

## Vehicle

The pending release is **1.36.2** (patch):

- latest tag **1.36.1** (`90c5ffb8`); `master:version` still `NXT_VERSION=1.36.1` /
  `NXT_VERNUM=13601` (not bumped).
- `CHANGES` top block **"Changes with FreeUnit 1.36.2 — 30 Aug 2026"** is open and
  already carries the shared-memory hardening (read-once records + the `UINT32_MAX`
  segment id) — i.e. **#445 / #505 are folded into 1.36.2**.

Reminder (project rule): **patch = security / DoS only; features, API and breaking
changes go to a minor.** (The intern's original 1.36.2 plan carried 2 Feature entries —
that is exactly why it is really 1.37.0 material; see the split note elsewhere.)

## Triage of #508/#515–#523

### Security / DoS → must be in a patch (1.36.2)

| PR | What | Draft? |
|----|------|--------|
| **#508** | http: add `body_min_rate` + `send_min_rate` — `body_read_timeout`/`send_timeout` are **gap timers**, so a byte just before each deadline holds a connection forever (slow POST / slow read). `header_read_timeout` is a single budget and is unaffected. **This is the exact gap vs Buran's `min_body_rate`.** | **ready** |
| **#515** | fix(isolation): unshare the **cgroup namespace after** the cgroup move — with `namespaces.cgroup: true` the app's `/proc/self/cgroup` was rooted at the main process (`0::/scope/python` instead of `0::/`). Containment. | **ready** |
| **#517** | wasm: check the guest `malloc` result against the **linear memory size** — the guest i32 was sign-extended into `size_t`, moved the host base below linear memory, and the first request wrote the header **out of bounds**. Sandbox memory corruption. | draft |
| **#520** | regex: cap a pattern's match work at **1,000,000 steps** — `pcre2_match()` ran with no limit; `^/(.*)/(.*)[xy]$` backtracks quadratically → ~167 ms **router CPU per request** on an 8 KiB URI → ReDoS thread stall (and the log echoed the full URI). | draft |
| **#521** | isolation: create mount destinations **without following symlinks** — `nxt_fs_mkdir_p()` followed a symlink, letting a writable-rootfs app make the prototype create dirs **outside the rootfs as root** (escape); pre-openat2 it also mounted the unchecked path. | draft |
| **#522** | http: bound **WebSocket pings** answered per connection — the router PONGs every PING without waiting for the write side, so a PING-flood + slow read grows the pending write queue without limit. New option `settings/http/websocket/max_pings`. | draft |

### Bugfix (not security) → next patch

| PR | What | Draft? |
|----|------|--------|
| **#518** | php: **free the root path buffer** when `realpath()` fails (leak) + two wrong route comments. | draft |
| **#519** | port: never hand out **RPC stream 0** after the 32-bit counter wraps — wrapped callers treat 0 as failure and skip `nxt_port_rpc_cancel()`, leaking handler registrations. Needs 2^32 ops to reach. | draft |

### Feature / perf → minor (1.37.0)

| PR | What | Draft? |
|----|------|--------|
| **#523** (issue **#516**) | main: store the atomic state files in a **short-lived child process** — the two `fsync()` per stored file run in the event loop; a reconfigure on pro4s-4 took 19.1 → 42.2 ms and SIGTERM 5.0 → 17.4 ms. | **ready** |

## Recommendation

- **Patch now (ready, high value):** **#508** (closes the slow-POST/slow-read hole we
  traced against Buran) and **#515** (cgroup-ns containment). Both non-draft.
- **Land before the tag once reviewed:** #517, #520, #521, #522 — all four are
  security/DoS and belong in a patch; they are still drafts, so finishing them is the
  gating step. #521 (rootfs escape) and #517 (wasm OOB) are the most severe.
- **Not for the patch:** #518 / #519 (bugfix/leak) → next patch; **#523 / #516** is a
  perf change → 1.37.0.
