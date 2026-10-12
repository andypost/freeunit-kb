# zen-quorum: PR #254 — capability: keep running when capget() is filtered
_gathered 2026-09-03 · keyless OpenCode Free tier_

**PR:** capability: keep running when capget() is filtered
**Body:**
```
`unitd` refused to start whenever the `capget()` syscall was denied: a
non-root process got `[alert] failed to get process capabilities` and
exited. A syscall filter that omits `capget` is the trigger — a systemd
`SystemCallFilter=` allowlist, a `bwrap --seccomp` sandbox, or a
hand-written OCI profile on a runtime that does not itself need the call.

Unit now warns and continues, assuming no capability.

## What this is, and what it is not

Hardening, not an adoption blocker. The claim that Docker's default seccomp
profile blocks `capget` — recorded as a P0 in the internal audit matrix —
**is false and this PR supersedes it**: Moby's `default.json` allows
`capget` by name (so it is arch-independent), a profile that denies it kills
`runc` before `unitd` ever runs, and the official image runs as root, where
`nxt_capability_set()` short-circuits and never calls `capget` at all. No
such failure was ever reported against this project or upstream. The
correction to the KB is written up separately in `kb-correction-capget-a4.md`.

Design and verification notes: `plan-capget-fallback.md`.

## The errno set is deliberately narrow

Only `EPERM` and `ENOSYS` — the signatures a filter reports through
`SECCOMP_RET_ERRNO` — fall through to the warning. Every other errno keeps
the alert and the non-zero exit, because `EINVAL` or `EFAULT` means the call
itself is malformed: a bug in Unit rather than a policy decision by the
operator, and failing closed is right there.

An unconditional "unknown means none" would have been wrong. With
`setid == 0` the runtime never resolves credentials and never calls
`setgid()`/`setuid()`, and an application's `user` is only string-compared
against `--user`, so a `unitd` that genuinely held `CAP_SETUID` with
`capget` filtered would run every application as its own uid while the
configuration said otherwise — a silent downgrade.

## The warning has to survive daemonisation

`nxt_capability_set()` runs from `nxt_runtime_conf_init()`, before
`nxt_runt
```

## Opinions
- **laguna-s-2.1-free** (2.8s): VERDICT=CORRECT · CONCLUSION=CLEARED · RISK=low — narrow errno handling and deferred logging are robust · CONFIDENCE=high
- **ling-3.0-flash-fin-free** (12.5s): VERDICT=PARTIAL · CONCLUSION=PARTIALLY-CLEARED · RISK=low — the described fallback logic is well-reasoned, but untested code and incomplete documentation leave some uncertainty · CONFIDENCE=medium
