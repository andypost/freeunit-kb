# Plan: capget fallback in nxt_capability.c (roadmap A4)

Status: 2026-08-29, post-release master work (1.36.1 tagged; origin/master @ d8feac33 — no capability/runtime files changed since 9f458653).
Supersedes `issues-p0/p0-capget-prod.md`, whose premise was verified false (§1).
Review history: Fable empirical verification (§1); local codex (gpt-5.6-sol, high) plan review folded in — its findings changed §2/§3 materially.

## 1. What is actually true (verified 2026-08-29, docker 29.7.2, `ghcr.io/freeunitorg/freeunit:latest-minimal`, amd64)

| scenario | result |
|---|---|
| default run | HTTP 200. Image runs as **root** (`Config.User` empty; `pkg/docker/Dockerfile.minimal:89-115` creates uid 999 `unit` but never `USER`s it). `nxt_capability_set()` short-circuits on `geteuid()==0` (`src/nxt_capability.c:52-55`) — capget is never called. |
| `--user 1000` | exit 1 on `mkdir(/var/lib/unit/certs/) failed (13)` / `bind(unix:/var/run/control.unit.sock.tmp) failed (13)`. Filesystem ownership, not capget. |
| `--user 1000 --cap-drop=ALL --security-opt no-new-privileges` + tmpfs on /var/lib/unit and /var/run | starts (`unit 1.36.1 started`, router started). Direct `syscall(125)` probe: ret 0. |
| Docker `--security-opt seccomp=<capget→EPERM/ENOSYS>` | **runc dies first** ("unable to get capability version from the kernel"). unitd never runs. |
| in-process BPF filter (static wrapper, non-root) capget→EPERM / ENOSYS | `[alert] failed to get process capabilities: (1|38)`, exit 1. The only trigger. |
| same filter, root | starts (short-circuit). |

- Moby `profiles/seccomp/default.json`: `capget` is in the unconditional `SCMP_ACT_ALLOW` list, matched by name → arch-independent. AppArmor does not mediate capget. gVisor implements it.
- No report exists: `gh issue list/search capget` on freeunitorg/freeunit and nginx/unit → empty; `"failed to get process capabilities"` → empty.
- Real trigger set: systemd `SystemCallFilter=` allowlists without capget, bwrap `--seccomp`, hand-rolled OCI profiles on a runtime that does not itself need capget (runc/crun do).
- Provenance of "A4": hermes-playground `kb-freeunit/engineering/audit-priority-matrix.md` row A4 ← `syscall-audit-kernel-requirements.md` §6.1 (KANBAN task 6, 2026-07-16) — an unreproduced assertion with a wrong workaround (`--cap-add SYS_PTRACE` does not affect capget). The P0 note transcribes it and adds invented details (`--user=unit` image, "arm64 syscall number", "`--cap-drop=ALL` cannot read own caps"). The only caller is `src/nxt_runtime.c:870` (not 855/857).
- Codex could not verify the docker/runc/moby/GitHub facts from the repo (expected — they are external); the scratchpad keeps the commands.

**Severity: hardening, not P0.** Ship a *narrow* fallback; keep the adoption-blocker framing out.

## 2. Code change (S) — narrowed after codex review

Why not "unknown → none, always": with `setid == 0` the runtime never resolves credentials (`src/nxt_runtime.c:874-885`) and never calls
setgid/setuid (`src/nxt_process.c:1100-1120`); app `user`/`group` are only string-compared against the `--user`/`--group` strings
(`src/nxt_isolation.c:100-128`, default app user copied from the string at `src/nxt_main_process.c:554-557`). Unit never calls `capset()`.
So a non-root unitd that *does* hold CAP_SETUID/SETGID (systemd ambient/file caps) but whose capget is filtered would silently keep its own
uid for every app while the config says otherwise, and would keep the unobservable capabilities. That is the existing "unprivileged" mode,
not an escalation — but it is a silent downgrade, and "continues as an unprivileged process" would be a false CHANGES line.

`src/nxt_capability.c`, `nxt_capability_specific_set()`, the `nxt_capget(&hdr, val) == -1` branch:
- `errno == EPERM || errno == ENOSYS` (the filter signatures) → `NXT_LOG_WARN`: `"capget() is blocked (%E); capabilities are unknown and
  will not be used: user/group switching and rootfs are disabled, applications run as uid %d"` → `return NXT_OK` (flags stay 0).
- any other errno (EINVAL/EFAULT = version/invariant bug) → keep the existing alert + `NXT_ERROR`.
- Do **not** touch `nxt_runtime.c:870`. The `"Unit is running unprivileged"` warn at `:882-884` still fires after the fallback — acceptable,
  the new warn precedes it and says why.
- Version probe `nxt_capability_linux_get_version()` already ignores failure — leave it. `#else` (non-Linux) arm untouched
  (`src/nxt_capability.c:123-129` returns NXT_OK with zero flags — same shape as the fallback).
- Optional hardening in the same PR (decide at implementation): on the fallback path, compare the configured `--user` with the actual
  `geteuid()` name and warn explicitly when they differ — that is the case codex flagged.
- Residual, documented in the commit message and CHANGES: unobservable capabilities are not dropped. Codex P1 on 9f0e5db0 proposed
  `capset(0)` on the fallback path; **rejected for this PR** (verified 2026-08-30): `nxt_capability_set()` runs in main from
  `nxt_runtime_conf_init()` (`src/nxt_runtime.c:125→870`) but main binds listeners later, in `nxt_main_listening_socket()`
  (`src/nxt_main_process.c:1294`, `bind()` at `:1345`, called from the SOCKET handler `:1240`) — dropping everything in main would strip
  `CAP_NET_BIND_SERVICE`, the one real systemd scenario, turning "fails at start" into "starts but cannot listen on :80". Capget being
  filtered means we cannot choose what to drop. See §4 item 5 for the correct place. Fail-closed remains for non-filter errnos.
- Note (`src/nxt_isolation.c:637-651`): `chroot == 0` *rejects* `rootfs` configs (loud), and a NEWUSER (`credential`) namespace
  overrides both flags (`:94-97`, `:642-645`, `src/nxt_process.c:1102-1107`) — so the warn/CHANGES text must be qualified: "disabled
  for applications that do not enable the credential namespace". (Review 2026-08-30 caught the unqualified wording in 9f0e5db0.)
- The warn is emitted from `nxt_runtime_conf_init()` (`src/nxt_runtime.c:125→870`) BEFORE `unit.log` is opened
  (`nxt_runtime_log_files_create`, `:356`), so it only reaches stderr — verified empirically. Record a flag and re-emit after the log
  opens, or the "silent downgrade" rationale only holds for foreground starts; the smoke test must assert on unit.log after that fix.

## 3. Tests (honest scope)

- pytest cannot mock syscalls; `LD_PRELOAD` cannot intercept `syscall(SYS_capget)` (`src/nxt_capability.c:35-36`); a Docker seccomp
  profile kills runc. Not viable in-suite.
- Viable: `secexec.c` wrapper in `~/www/freeunit-harness/tools/`: `prctl(PR_SET_NO_NEW_PRIVS)` + `SECCOMP_MODE_FILTER` BPF returning
  `SECCOMP_RET_ERRNO|<errno>` for `SYS_capget`, errno selectable (EPERM and ENOSYS both exercised), **with** an `AUDIT_ARCH` check
  (compile `SYS_capget` per target; omitting the arch check is unsafe across compat ABIs, not "portable"). Dynamic link is fine; `-static`
  only if the runner lacks the libc.
- Run `build/sbin/unitd --no-daemon` unprivileged under it with the same temp `--statedir/--pid/--log/--control/--tmpdir` the suite
  uses (`test/conftest.py:493-513`) — a bare invocation fails on filesystem perms before reaching the fallback.
- Assert: new `[warn]` present; `router started`; **load a trivial app and check its actual uid/gid/groups** (`/proc/self/status`
  via a python app) — the control-socket 200 alone does not cover the downstream path codex flagged. Two variants: (a) no caps +
  filter (must start, app uid == unitd uid); (b) with CAP_SETUID/SETGID granted (e.g. `capsh`/file caps or systemd
  `AmbientCapabilities`) + filter — documents the residual: starts with the warn, app uid == unitd uid, no escalation.
- Non-filter errno path: not testable without fault injection; covered by code review.
- Regression: `test/test_go_isolation_rootfs.py`, `test/test_java_isolation_rootfs.py`, `test/test_python_isolation_chroot.py`,
  `test/test_python_isolation.py` (`test_rootfs` as a file does not exist).
- Alternative where a systemd user session exists: `systemd-run --user -p SystemCallFilter=~capget -p SystemCallErrorNumber=EPERM`.

## 4. Deliverables / sequencing

1. PR against master: `capability: continue without capabilities when capget() is filtered` (+ CHANGES: "unitd no longer exits when the
   capget() syscall is denied by a seccomp filter; it warns and runs without user switching and rootfs. Unobservable capabilities are not
   dropped."). Opus implements in a worktree; Fable/opus pre-PR review; local `codex review --uncommitted`; re-run `./configure` after codex.
2. Harness: `secexec.c` + smoke script (§3) — start in parallel with 1, it is 1's verification.
3. KB correction (hermes-playground): rewrite A4 / §6.1 to §1; downgrade. Delete `issues-p0/p0-capget-prod.md` (superseded by this file).
4. Separate roadmap item — the real non-root friction: `/var/lib/unit` and `/var/run` are root-owned in the image, so `--user` fails.
   Options: `chown unit` + `VOLUME`, or defaults under a uid-999-writable dir. Not part of this PR.
5. Separate item (from codex P1): **drop capabilities in the application child after fork**, in the child fixup path before the app
   runs (apps never need caps; main keeps NET_BIND_SERVICE for `bind()`): `capset` all-zero + `PR_CAP_AMBIENT_CLEAR_ALL`, independent of
   whether capget worked. Own plan + review — touches `src/nxt_process.c`/isolation, not this PR. Note ambient-clear alone is useless
   (workers are forked, not exec'd; permitted/effective inherit).

## 5. Acceptance

- [ ] Non-root unitd under a capget→EPERM and →ENOSYS filter starts, logs the new `[warn]`, serves a request; app runs as unitd's uid.
- [ ] Non-filter errno still exits with the alert (review).
- [ ] Root behaviour unchanged (no capget call). Non-root without filter: flag detection unchanged (isolation/rootfs tests green).
- [ ] CHANGES wording does not claim "unprivileged"; residual documented.
- [ ] KB row A4 no longer claims Docker default seccomp blocks capget.

## Agent briefing notes
opus implements; use `~/www/freeunit-harness` skills/tools for build+test; verify claims in this plan against `origin/master` (local master
is stale); no git state changes in the shared checkout — work in a worktree.
