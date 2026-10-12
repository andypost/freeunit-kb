# Readiness: capget + rootfs closure status (2026-09-06)

_Consolidated readiness for the two P0-adjacent security/isolation chains.
Distills gh state (PRs/issues) into "what still stands between us and closed".
Replaces scattered per-PR docs for the readiness question._

## Capget (#254) — READY to merge, NOT merged

**Chain is one PR that grew into the full fix + follow-up:**
`freeunitorg/freeunit#254` "capability: keep running when capget() is filtered",
**open**, +1024/−12, 9 files, 6 commits:

- `c04ff99` capget-fallback (warn+continue on EPERM/ENOSYS, narrow errno set)
- `88e1c8a` **capset-drop follow-up** — every forked child empties its
  permitted/effective/inheritable/ambient sets in `nxt_process_apply_creds()`
  (after setgid/setuid, unshare, mount/pivot_root/chroot, before app code).
  Fixes the **broader** non-filter-dependent capability leak (unitd handed all 4
  sets to every app even with a working capget). `PR_CAP_AMBIENT_CLEAR_ALL` first.
- `250d1ec` + `7ca2d99` tests: preload-shim records capset() callers; asserts
  main never drops, prototype drops, worker does not (structural, not vacuous)
- `e38fdf8` CI fix (no leg was running the capget test)
- `fd8ddb` changes.xml (1.36.2 stanza)

**Claude thorough-review (01.09, @TuzelKO):** *"The bug is closed, and the
follow-up security fix is correctly placed."* 6 findings, **none blocking** —
main two were changelog-omission + test-coverage gap (already present). Only
non-production concern: duplicated warning-verbatim (low, a shared macro would
make it structural).

**Verdict:** code-ready. Last activity 2026-09-01 (Claude). Not merged.
→ block = **operator decision to merge**, not code. Quorum decision was A
(warn+continue) — see `zen-quorum-capget-decision.md`.

## Rootfs — separate 3-piece chain, all open

| # | role | state |
|---|------|-------|
| **#274** | bug cause: rootfs + namespaces.credential w/o namespaces.mount accepted but can never start (automounts hit parent mount-ns → EPERM, kernel invariant) | open |
| **#279** | fix: reject that config at apply time. Narrower than "rootfs+credential" — rootfs alone falls back to chroot (needs only CAP_SYS_CHROOT); the reject triggers only when an automount would be attempted. +256/−1 (nxt_conf_validation.c +116, test +140) | open |
| **#278** | build: probe memfd_create() WITHOUT the kernel UAPI header — fixes the musl/Alpine miss so libunit does NOT silently fall back to shm_open() (which breaks every isolation.rootfs app). +97/−5, 8 files (auto/shmem, nxt_port_memory.c, nxt_unit.c, test) | open, updated 09-06 |

**Chain is now fully covered by 3 PRs:** #274 (describes the bug) is gated by
#279 (config reject) for the mount-ns EPERM half, and by #278 (memfd probe) for
the shm_open-rootfs-death half. All open, none merged. #278 opened 09-06 — the
live fix for the Alpine build-blocker.


**Rootfs readiness:** #279 not reviewed yet (only opened 09-05). #273 is a
build-level blocker that breaks rootfs apps on Alpine — it likely gates the
rootfs story more than #279 does.

## What the digest SHOWED vs reality
Digest (09-06) showed #276 merged + #292/#293 (EADDRINUSE/port-test, an
offshoot of the #276 listener theme). It did **not** surface:
- capget #254 (ready, unmerged — the actual pending P0)
- capset-drop follow-up inside it
- rootfs chain #279/#274/#273

**Lesson:** the change-track digest tracks merge-activity, not "critical chain
readiness". For readiness, query the KB graph / gh state (this file), not the
daily digest.

## Why so many PRs came out of capget/rootfs (snowball / class effect)

_2026-09-06 observation. 33 PRs in window 250-293; only 6 are directly capget/
rootfs. The rest are the connected-defect class the two P0s opened._

**Capget is not one bug — it is a class on one contoured path**
(capset/capget/fork/cred + the same IPC port/process path):
- #254 capability fallback (the fix itself)
- #255 clear proto_port_requests (process-start path)
- #253 port auth by kernel pid (adjacent same port/process path)

**Rootfs is not one bug — 4 axes, 4 PRs** (mount ns + automount + memfd + cred):
- #259 test-side (timezone db)
- #265 product fix (automount.language_deps)
- #278 build fix (memfd_create probe, musl/Alpine)
- #279 config reject (rootfs+credential w/o mount ns)

**Why it snowballs (root cause, not a bug):**
- capget & rootfs are SYSTEMIC problems (cap visibility, mount-namespace, build
  detection). Fixing a systemic defect opens N adjacent defects on the same
  contour, not one isolated case.
- The 09-05 wave (#277-291) is NOT all capget/rootfs — it is clearing adjacent
  defects found en route (router listener, http compression, access-log, state
  files, START_PROCESS reply, app-start bound). Same PORT/PROCESS/ROUTER/HTTP
  zone, but distinct defects.
- Small verifiable PRs (one per change) is the CORRECT practice — not one
  giant PR. 33 small PRs ≠ noise; #284 (access-log), #287 (port lock), #281
  (engine-quit job) each carry a real fix.

**Classification (250-293):** capget/rootfs direct = 6 · CI/test/build = 9 ·
adjacent (port/process/router/http) = 18.

## Related
- `engineering/zen-review-pr-254.md` — merge review of #254
- `engineering/zen-quorum-capget-decision.md` — quorum chose variant A
- `engineering/capget-fallback-plan.md` — A/B/C/D options
- `engineering/zen-review-pr-276.md` — router listener (the digest's focus)
