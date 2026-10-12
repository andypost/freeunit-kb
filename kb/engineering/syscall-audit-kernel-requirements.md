# Syscall Audit & Kernel Requirements — FreeUnit 1.35.6

_Audit date: 2026-07-16 | Branch: pre-1.35.6 (19fe644)_

---

## 1. Direct Syscalls (via `syscall()` wrapper)

| Syscall | Min Kernel | Fallback | Usage |
|---------|-----------|----------|-------|
| `SYS_openat2` | 5.6 | `ENOSYS` → graceful degrade with warning | Rootfs isolation (RESOLVE_BENEATH) + file open |
| `SYS_pivot_root` | 2.6+ | `#if` guard (`NXT_HAVE_LINUX_PIVOT_ROOT`) | Rootfs isolation with NEWNS |
| `SYS_memfd_create` | 3.17 | — | Shared memory for port communication |
| `SYS_capget` / `SYS_capset` | 2.6+ | `#if` guard (`NXT_HAVE_LINUX_CAPABILITY`) | Capability detection (read-only) |
| `SYS_getrandom` | 3.17 | `getrandom()` glibc → `getentropy()` | Key generation in nxt_random |
| `SYS_gettid` | 2.6+ | `gettid()` glibc wrapper | Thread ID (debug/logging) |

## 2. Library Wrappers (glibc → syscall)

| Function | Min Kernel | Usage |
|----------|-----------|-------|
| `fork()` | 2.6+ (POSIX) | Process spawning — **no `clone3`** |
| `epoll_create` / `epoll_ctl` / `epoll_wait` | 2.6+ | Event engine (Linux event loop) |
| `prctl(PR_SET_CHILD_SUBREAPER)` | 3.4 | Process tree management |
| `prctl(PR_SET_NO_NEW_PRIVS)` | 3.5 | App process security |
| `mount()` | 2.6+ | Custom filesystem mounts for apps |
| `umount2()` | 2.6+ | Cleanup on app exit |
| `signalfd()` | 2.6.27 | Signal handling |
| `eventfd()` | 2.6.27 | Event notification |
| `sendfile()` | 2.6+ | Zero-copy static file serving |
| `fcntl()` | POSIX | FD flags (CLOEXEC, NONBLOCK) |
| `socketpair()` / `socket()` | POSIX | IPC / listener sockets |

## 3. Namespace Flags (compile-time optional)

| Flag | Guard | Feature |
|------|-------|---------|
| `CLONE_NEWUSER` | `NXT_HAVE_CLONE_NEWUSER` | User namespace |
| `CLONE_NEWPID` | `NXT_HAVE_CLONE_NEWPID` | PID namespace |
| `CLONE_NEWNET` | `NXT_HAVE_CLONE_NEWNET` | Network namespace |
| `CLONE_NEWUTS` | `NXT_HAVE_CLONE_NEWUTS` | Hostname namespace |
| `CLONE_NEWNS` | `NXT_HAVE_CLONE_NEWNS` | Mount namespace |
| `CLONE_NEWCGROUP` | `NXT_HAVE_CLONE_NEWCGROUP` | Cgroup namespace |

All namespacing is `#if`-guarded at build time; no runtime probe.

## 4. NOT Used (not yet)

- `clone3` — FreeUnit uses `fork()`; no `clone()` or `clone3()` anywhere
- `io_uring` — not implemented
- `seccomp` — only mentioned in comments; no `prctl(PR_SET_SECCOMP)` or `seccomp()`
- `close_range()` / `closefrom()` — not used
- `timerfd_create()` — not used
- `pidfd_open()` / `pidfd_send_signal()` — not used
- `landlock` — not used
- `bpf()` / `bpf2()` — not used

## 5. Minimum Kernel Requirements

| Level | Kernel | Reasoning |
|-------|--------|-----------|
| **Build (min)** | 3.4 | `PR_SET_CHILD_SUBREAPER` (3.4), `PR_SET_NO_NEW_PRIVS` (3.5) |
| **Build (recommended)** | 5.6 | `SYS_openat2` for rootfs symlink guard |
| **Runtime (all features)** | 5.6 | Full isolation (openat2 + new enough ns) |
| **Runtime (graceful)** | 3.17 | Falls back on openat2 → symlink warning, everything else works |

### Kernel support matrix

| Feature | Linux < 3.4 | 3.4–3.16 | 3.17–5.5 | 5.6+ |
|---------|-------------|----------|----------|------|
| `fork()` + epoll | ✓ | ✓ | ✓ | ✓ |
| `PR_SET_CHILD_SUBREAPER` | ✗ No child reaper | ✓ | ✓ | ✓ |
| `SYS_memfd_create` | ✗ No shared mem | ✗ | ✓ | ✓ |
| `SYS_getrandom` | ✗ Fallback poor | ✗ | ✓ | ✓ |
| `SYS_openat2` | ✗ No rootfs guard | ✗ | ✗ | ✓ |

> **Distro baseline:** RHEL 8 (4.18), Debian Buster (4.19), Ubuntu 20.04 (5.4) — all at least 4.x. Openat2 (5.6) is the only truly modern gate. Production recommend: **RHEL 9+ / Debian Bullseye+ / Ubuntu 22.04+**.

## 6. Docker / Seccomp Interaction

### Docker default seccomp profile — per-syscall status

| Syscall | Default allow? | Impact |
|---------|---------------|--------|
| `fork()` | ✅ Allowed | — |
| `epoll_create` / `epoll_ctl` / `epoll_wait` | ✅ Allowed | — |
| `signalfd()`, `eventfd()` | ✅ Allowed | — |
| `sendfile()` | ✅ Allowed | — |
| `prctl()` (CHILD_SUBREAPER, NO_NEW_PRIVS) | ✅ Allowed | — |
| `getrandom()` | ✅ Allowed | — |
| `memfd_create()` | ⚠️ Partially | Allowed in Docker ≥20.10; blocked on older |
| `openat2()` | ⚠️ Varies | Allowed in Docker ≥25.x (moby#45988); **blocked on <25.x** |
| `capget()` / `capset()` | ❌ **Blocked** | See §6.1 |
| `mount()` | ❌ **Blocked** | Needs `--security-opt seccomp=unconfined` or custom profile |
| `pivot_root()` | ❌ **Blocked** | Needs `--security-opt seccomp=unconfined` or custom profile |

### 6.1 Critical: `capget` blocked for non-root containers

`nxt_capability.c` calls `capget` via `syscall(SYS_capget)` when `geteuid() != 0`:

```c
if (geteuid() == 0) {
    cap->setid = 1;    // skipping capget — works in root containers
    return NXT_OK;
}
// non-root: invokes capget → blocked by Docker seccomp → EPERM
```

When `capget` returns `EPERM` (Docker default seccomp):
- `nxt_capability_specific_set()` → `NXT_ERROR`
- `nxt_runtime.c:855` catches this → **FreeUnit fails to startup**

**Workarounds:**
1. Run as `root` inside container (UID 0) — bypasses `capget` entirely
2. `--security-opt seccomp=unconfined` or custom seccomp with `capget`/`capset` allowed
3. `--cap-add SYS_PTRACE` — Docker ≥23.x includes `capget` when `SYS_PTRACE` is granted

Upstream NGINX Unit docs already advise running `unitd` as root inside containers (it drops privileges itself). This is consistent.

### 6.2 App isolation inside Docker containers

If FreeUnit runs inside Docker and an application config requests:
- **`rootfs`** with `"mounts"` — requires `mount()` + `pivot_root()` → ❌ blocked
- **`rootfs`** without mounts (chroot-only) — requires `chroot()` → ✅ works
- **Namespaces** (NEWPID, NEWNET, NEWNS) — requires `clone()` flag bits in `fork()` → ⚠️ `clone3` not used, `fork()` own NS bits are inherited correctly but some flags (`CLONE_NEWNS`) need `SYS_ADMIN` capability
- **User namespace (NEWUSER)** — requires `SYS_ADMIN` or `--privileged` inside Docker

**Summary for Docker deployment:**

| Use case | Works in default Docker? | Requires |
|----------|------------------------|----------|
| Static files | ✅ Yes | — |
| PHP / Python apps (no isolation) | ✅ Yes | Container runs as root |
| PHP / Python apps + simple chroot | ✅ Yes | — |
| PHP / Python apps + mount isolation | ❌ No | `--security-opt seccomp=unconfined` or custom profile |
| PHP / Python apps + rootfs + pivot | ❌ No | `--security-opt seccomp=unconfined` or `--privileged` |
| Capability detection (non-root) | ❌ No | Run container as root (UID 0) |

### 6.3 Debian Trixie specifics

Debian Trixie (kernel 6.x) backport notes:
- No new syscall compatibility issues for FreeUnit's current profile
- Docker on Trixie ships with updated seccomp profile (includes `openat2` if Docker ≥25)
- `capget` remains blocked in default profile — same fix as §6.1
- Kernel headers in Trixie enable all namespace flags at build time reliably

---

## 7. Granular seccomp profile for FreeUnit in Docker

Minimal custom seccomp profile (JSON) to unblock all FreeUnit features in Docker:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": [
        "accept", "accept4", "access", "bind", "brk", "capget", "capset",
        "chdir", "chroot", "clone", "close", "connect", "dup", "dup2",
        "epoll_create", "epoll_create1", "epoll_ctl", "epoll_wait",
        "eventfd2", "execve", "exit", "exit_group", "fchdir", "fcntl",
        "fstat", "fsync", "ftruncate", "futex", "getdents64", "geteuid",
        "getpeername", "getpid", "getrandom", "getsockname", "gettid",
        "ioctl", "listen", "lseek", "memfd_create", "mkdir", "mmap",
        "mount", "mprotect", "munmap", "nanosleep", "newfstatat",
        "open", "openat", "openat2", "pipe2", "pivot_root",
        "poll", "ppoll", "prctl", "read", "readlink", "readv",
        "recvfrom", "recvmsg", "rename", "rt_sigaction", "rt_sigprocmask",
        "sched_yield", "sendfile", "sendmmsg", "sendmsg", "sendto",
        "set_robust_list", "set_tid_address", "setgid", "setgroups",
        "setsockopt", "setuid", "shutdown", "signalfd4", "socket",
        "socketpair", "stat", "statx", "symlink", "syncfs", "sysinfo",
        "umask", "umount2", "uname", "unshare", "utimensat", "vmsplice",
        "wait4", "write", "writev"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

Usage: `docker run --security-opt seccomp=freeunit-profile.json ...`

---

## 8. Recommendations

1. **Document kernel baseline** — Document 5.6 as minimum for full feature set, 3.17 as minimum for basic operation
2. **Document Docker seccomp guidance** — Add Dockerfile note: `USER root` (not non-root) for official images, or ship a custom seccomp profile
3. **Consider `capget` fallback** — Make `capget` failure non-fatal for non-root containers (treat blocked capget as "no capabilities", continue without setid/chroot)
4. **No `clone3` needed** — FreeUnit's `fork()`-based model avoids the Docker seccomp `clone3` conflict entirely (good)
5. **io_uring not on horizon** — Not in pre-1.35.6; when adding, it will require kernel 5.1+ and a new Docker seccomp exception
6. **Add syscall audit to CI** — Add a CI job that builds on Alpine/musl and runs `strace -c unitd` to detect syscall drift
7. **Test matrix** — Add Docker integration tests: default seccomp + root, custom seccomp + isolation, Trixie host

## 9. Docs check via Context7 (2026-10-11)

The Linux kernel documentation corpus confirms **semantics but not version floors**: asked for
`io_uring`, `epoll_pwait2` and `MSG_ZEROCOPY` it returns the API descriptions and their constraints
(a zerocopy buffer must not be modified while the send is in flight; a kTLS control message on
receive needs a cmsg buffer or the receive errors) and **no "since Linux N.N" sentence anywhere**.
Recommendation 5's "kernel 5.1+" therefore still rests on the man-pages reading; treat it as
unverified-by-docs, not as wrong. Wrapper and corpus limits: the `context7-docs` skill.
