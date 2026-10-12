# io_uring Availability by Distribution (and why the engine stays opt-in)

**Created:** 2026-09-28
**Context:** follow-up to the io_uring engine investigation (PRs #30–32, `andypost/unit`).
Answers: "which distros can actually run it, and which tier do they reach?"

Two independent gates, in this order:

1. **Kernel capability** — which tier the kernel can serve.
2. **Policy** — distro default and container seccomp (this one fires far more often).

## Tier floors (from the engine's runtime probes)

| Tier | Needs | Feature |
|------|-------|---------|
| POLL (floor) | kernel ≥ 5.13 | multishot `IORING_OP_POLL_ADD` |
| ACCEPT | kernel ≥ 5.19 | `IORING_OP_ACCEPT` (oneshot) |
| RECV | kernel ≥ 6.0 | buf_ring + `IORING_RECV_MULTISHOT` — **deferred in C**, see `fix-recv-tier-kernel-6` |
| OPT | — | `SINGLE_ISSUER` + `DEFER_TASKRUN` — **dropped** (ring created on router-main, polled on worker → busy-loop on `-EEXIST`) |

Below 5.13 the engine degrades to epoll by probe. So "io_uring present in the kernel"
is not the same as "the engine registers".

## Per-distribution matrix (verified 2026-09-28)

| Distribution | Kernel | io_uring default | Max tier reachable |
|---|---|---|---|
| Ubuntu 20.04 LTS | 5.4 | enabled | below floor → epoll |
| Ubuntu 22.04 LTS | 5.15 | enabled | POLL |
| Ubuntu 24.04 LTS | 6.8 | enabled (`io_uring_disabled=0`; sysctl backported here) | POLL + ACCEPT |
| Ubuntu 26.04 LTS | 7.0 | enabled (no io_uring hardening in release notes) | POLL + ACCEPT |
| Debian 11 bullseye | 5.10 | enabled | below floor → epoll |
| Debian 12 bookworm | 6.1 | enabled (no `io_uring_disabled` file — knob landed in 6.6) | POLL + ACCEPT |
| Debian 13 trixie | 6.12 | enabled | POLL + ACCEPT |
| RHEL / Rocky / Alma / Oracle / CloudLinux 8 | 4.18 | **absent** (io_uring started at 5.1) | none |
| RHEL / rebuilds 9 | 5.14 | **disabled by default** — Tech Preview, `kernel.io_uring_disabled=2` since 9.3, `io_uring_group` in 9.4 | POLL (if an admin sets 0/1) |
| RHEL / rebuilds 10 | 6.12 | **disabled by default** — still Tech Preview, `=2` | POLL + ACCEPT (if set 0) |
| Fedora | 6.8+ | enabled (`CONFIG_IO_URING=y`) | POLL + ACCEPT |
| SLES / openSUSE Leap 15.6 | 6.4 | enabled by default (`io_uring_group=-1`; `=2` seen on the forum is a local `/etc/sysctl.conf` choice) | POLL + ACCEPT |
| Amazon Linux 2023 | 6.1 / 6.12 / 6.18 (default → 6.18 on new AMIs since 2026-08-17) | enabled | POLL + ACCEPT |
| Alpine 3.21 / 3.22 | 6.12 (`linux-lts`) | enabled | POLL + ACCEPT |
| Android / ChromeOS / Google prod | — | **blocked for apps / disabled** (Google: 60% of 2022 bug-bounty kernel exploits targeted io_uring) | none |

`kernel.io_uring_disabled` semantics (upstream since 6.6):
`0` = all processes; `1` = only `CAP_SYS_ADMIN` or members of `kernel.io_uring_group`;
`2` = creation disabled for everyone (`io_uring_setup()` → `-EPERM`). The knob is **not
retroactive** — existing rings keep working.

## Container / orchestrator layer (decides more often than the distro)

- **Docker default seccomp profile**: `io_uring_setup` is in the deny list
  (moby/moby#46762, 2024) "due to security vulnerabilities that can be exploited to
  break out of containers". All three syscalls — 425 `io_uring_setup`,
  426 `io_uring_enter`, 427 `io_uring_register` — are outside the allowlist.
- **containerd**: same profile.
- **Kubernetes**: `RuntimeDefault` + CIS guidance explicitly recommend blocking the
  three io_uring syscalls.
- **gVisor**: io_uring is not implemented at all — no seccomp override helps.

**Measured on our own stand (2026-09-28):** Alpine 3.25 container under Docker, host
kernel 6.8.0 (`kernel.io_uring_disabled = 0`), container `Seccomp: 2` with one filter
applied. Direct probe: `io_uring_setup(8)` → `-1 EPERM`. So a host with io_uring fully
enabled still gives the engine nothing inside the default container; it would need
`--security-opt seccomp=unconfined` (or a custom profile allowing 425/426/427).

## Consequence for FreeUnit

1. **epoll must stay the default.** The engine's design of "probe with functional test,
   degrade to epoll on probe failure or `create()` failure, `NXT_IO_URING=0` kill-switch"
   is not belt-and-braces — on RHEL/EL 9/10 (the enterprise default) and in any default
   container it is the *only* path that runs.
2. **Enterprise distros are the worst case, not the best.** RHEL-family defaults to
   `io_uring_disabled=2`, so the engine would be dead code there unless an operator opts in
   — and on EL9 even then it reaches only POLL.
3. **Tier probing must never parse `uname`.** A 7.0 kernel in a container is EPERM; a 5.14
   RHEL kernel with sysctl 0 is POLL-capable. Version parsing gets both wrong.
4. **The container is the real target for our Docker distribution.** Shipping an
   io_uring engine that needs `seccomp=unconfined` trades the container's main isolation
   control for a parity-minus win (`io-uring-ab-benchmark-approach`: no scenario beat
   epoll; `proxy_ka` −8.7% RPS / +11.3% CPU). Documented escape hatch, not a default.
