# FreeUnit seccomp / Docker / Isolation — Plan Summary

**Source:** https://gist.github.com/andypost/3ff355322648302bde6fafcff15b7e1e
**Status:** DECIDED — maintainer approved all 4 deliverables
**Scope:** FreeUnit's syscall footprint vs Docker's default seccomp profile + Debian Trixie

---

## 1. Key Findings

### 1.1 FreeUnit uses fork(), not clone3()

```
src/nxt_process.c:553 — pid = fork();  ← main spawn path
src/nxt_process.c:470 — fork() inside nxt_process_unshare()  ← PID namespace double-fork
src/nxt_process.c:1127 — fork() in daemonization helper
```

**No** `clone(2)`, `clone3(2)`, `vfork()` used for spawning children.
Zero hits for `clone3` or `SYS_clone3` across src/ and auto/.

**Implication:** FreeUnit cannot trigger the glibc-2.34 "silent clone3 fallback"
class of failure that broke gVisor/Podman.

**Verified D1** on `debian:trixie` (glibc 2.41-12+deb13u3):
```c
// fork() under strace shows:
clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|CLONE_CHILD_SETTID|SIGCHLD, ...)
// One syscall: clone. No clone3. No legacy fork(2) trampoline.
```

### 1.2 Isolation uses unshare() after fork, not clone(CLONE_NEW*)

FreeUnit's `isolation` block applies namespaces via `unshare(2)` AFTER fork:

```c
// src/nxt_process.c:448
ret = unshare(process->isolation.clone.flags);
```

| Config key | Flag | Syscall |
|------------|------|---------|
| credential | CLONE_NEWUSER | unshare |
| pid | CLONE_NEWPID | unshare |
| network | CLONE_NEWNET | unshare |
| uname | CLONE_NEWUTS | unshare |
| mount | CLONE_NEWNS | unshare |
| cgroup | CLONE_NEWCGROUP | unshare |

Then mount/rootfs setup uses: `mount()`, `umount2()`, `pivot_root()`,
`openat2()`, `chroot()`.

**All of these are blocked by Docker's default seccomp profile.**

### 1.3 No app-level seccomp from FreeUnit

- Zero `prctl(PR_SET_SECCOMP, ...)` calls
- Zero `seccomp(2)` syscall
- Zero libseccomp linkage
- The only `seccomp` string in C sources is a comment documenting the design choice

### 1.4 What Docker's default profile blocks

| Syscall | Docker default | FreeUnit needs |
|---------|---------------|----------------|
| mount | ❌ Denied | ✅ isolation with rootfs |
| umount2 | ❌ Denied | ✅ isolation cleanup |
| pivot_root | ❌ Denied | ✅ isolation rootfs |
| unshare | ⚠️ Needs CAP_SYS_ADMIN | ✅ isolation namespaces |
| openat2 | ❌ Denied | ✅ symlink-escape guard |
| clone3 | ✅ Allowed | ❌ Not used (uses fork+clone) |
| personality | ✅ Subset | ❌ Not used |

### 1.5 Debian Trixie

- **D2 confirmed:** Trixie does NOT restrict unprivileged user namespaces by default
  (unlike Ubuntu 24.04+ with `apparmor_restrict_unprivileged_userns=1`)
- `kernel.unprivileged_userns_clone=1` (enabled since Debian 8/9)
- Ships Linux 6.12 LTS
- glibc `fork()` uses `clone`, not `clone3` (verified)

---

## 2. Four Approved Deliverables

### 2.1 Documentation (pkg/docker/README.md)

Add section "Running isolation under Docker" documenting:
- `isolation` needs `unshare`, `mount`, `umount2`, `pivot_root`, `openat2`
- All blocked by Docker's default seccomp
- `CAP_SYS_ADMIN` required (via `--cap-add=SYS_ADMIN`)
- Two copy-paste recipes:
  - `--privileged` (blunt, not recommended, disables all seccomp)
  - `--cap-add=SYS_ADMIN --security-opt seccomp=/usr/share/unit/seccomp-isolation.json`

### 2.2 pkg/docker/seccomp-isolation.json

Ship a new seccomp profile (default-deny allow-list, opposite shape to existing
`seccomp-no-af-alg.json`). Contains Docker's default allow-list PLUS:
- `mount`, `unshare`, `umount2`, `pivot_root`, `chroot`, `openat2`

**Caveats:**
- Profile alone does NOT grant capabilities — `--cap-add=SYS_ADMIN` still needed
- Drift liability: must be resynced when Docker updates its `default.json`
- Test matrix: every `isolation.namespaces.*` subflag under this profile

### 2.3 Code: EPERM Diagnostics + Fail-Fast

Replace generic `nxt_alert("mount() failed: %E")` with informative messages:
```
"isolation: unshare() denied (EPERM) — this process needs CAP_SYS_ADMIN
 and a seccomp/AppArmor policy permitting namespace/mount syscalls"
```

Add respawn-loop protection: after 2-3 consecutive EPERM exits for the same
app slot, stop retrying and escalate to a single fatal alert.

### 2.4 systemd .service hardening

Start as **doc snippet** (not default). Proposed directives:
- **Safe:** `ProtectKernelLogs=yes`, `ProtectHostname=yes`, `LockPersonality=yes`
- **Tricky (must preserve for isolation):** `CapabilityBoundingSet=` (keep
  `CAP_SYS_ADMIN`), `RestrictNamespaces=` (allow `CLONE_NEW*`), `SystemCallFilter=`
  (include `mount`/`unshare`/`pivot_root`)
- **Future:** ship as defaults after testing on real isolation configs

---

## 3. Open Items (need real hardware)

| Gap | What's needed |
|-----|---------------|
| D1 glibc fork | Verify if Trixie's pinned glibc version changes |
| D2 Trixie userns | Real Trixie on bare metal / VM (not container sharing host's kernel) |
| 7.3(ii) respawn protection | Design review + implementation in nxt_main_process.c |
| 7.2 seccomp-isolation.json | Run test matrix on Docker/runc versions FreeUnit supports |
| 7.4 systemd directives | Test with real isolation config on each target distro |
