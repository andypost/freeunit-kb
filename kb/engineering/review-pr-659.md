---
title: Review — FreeUnit PR 659 (mountinfo scan past unrelated cgroup2 mounts)
description: Verdict APPROVE for the cgroup2 mountinfo fix; evidence, test coverage, two nits.
tags: [review, cgroup, mountinfo, pr-659]
status: final
---

# Review: PR 659 — lib: keep scanning mountinfo past unrelated cgroup2 mounts

Head judged: `af1b9be3` (repo `freeunitorg/freeunit`, branch of PR 659).
Base: `origin/master` at `678ef06d`.
Diff: 5 files, +203/−27. Verdict: **APPROVE** (no blockers, two nits).

## What it does

`unitd` read only the first cgroup2 mount in `/proc/self/mountinfo` and gave up if
that mount's root did not contain its own cgroup, so the CPU limit was missed in a
mount namespace with several cgroup2 mounts. The scan is extracted into
`nxt_cgroup_mountinfo_find()`, which takes the first cgroup2 mount **whose root
contains the cgroup**, and `nxt_cgroup_cpu_limit()` now calls it.

## Correctness

- The cgroup2 filter lives in the parser, not the new loop:
  `nxt_cgroup_mountinfo_parse()` returns `NXT_DECLINED` unless the line carries
  `" - cgroup2 "` (`src/nxt_lib.c:374`), so "the first cgroup2 mount" is exact.
- `nxt_cgroup_relative_path()` returns NULL when the root is not a whole path
  component of the cgroup (it compares the prefix and requires `/` or `\0` after
  it, and rejects only whole `/..` components). The loop continues past those, which
  is the fix.
- The overflow check is the correct one (`len >= 0 && (size_t) len < size`);
  `base` is `strlen(mnt)`, the same value the walker received before, so the walk
  still stops at the mount root.
- `line` is freed on every exit; `getline` reuses the buffer across `continue`.

## Security and backward compatibility

No config, wire or ABI surface. The change can only *find* a limit that was
previously missed (it can also find one where `0` used to be returned, which is the
intent). No new parsing of untrusted input: `/proc/self/mountinfo` was already read.

## Tests

`src/test/nxt_cpu_limit_test.c` is pre-existing on master (registered in
`auto/sources:234`, called from `src/test/nxt_tests.c:498`, declared in
`nxt_tests.h:131`), and the PR extends it with `nxt_cpu_limit_find_test()`, Linux
guarded, built on `fmemopen()`. Nine cases, and the first one is the bug:

| # | Case | Expectation |
|---|---|---|
| 1 | first cgroup2 mount does not contain the cgroup, a later one does | the later mount wins (`/sys/fs/cgroup/app.slice/app`, base 14) |
| 2 | root `/app` versus cgroup `/app.slice/app` (prefix, not a component) | the second mount wins |
| 3, 4 | two mounts both contain the cgroup | first in file order wins |
| 5 | the mount root is the cgroup | `dir` = mount point, base 8 |
| 6, 7, 8 | no containing mount / no cgroup2 line / empty file | `NXT_DECLINED` |
| 9 | the directory does not fit in 32 bytes | `NXT_DECLINED` |

Case 1 fails on the pre-change code by construction: the old loop stopped at the
first cgroup2 mount and bailed out when the relative path was NULL. The buffer-size
assertion and the `NXT_LINUX` guard are both present.

CI on the head: `c-tests`, `c-tests-asan`, `c-tests-macos`, `c-tests-pcre1`,
`core`, `clang-ast`, `hardening-strict-fedora` (clang), `check-whitespace`,
`ast-grep baseline`, syscall-drift (glibc and musl) all pass.

## Findings

No blockers. Two nits, neither worth blocking the merge:

1. **The too-long path ends the search.** When a mount's root contains the cgroup
   but the resulting path does not fit, the function breaks and returns
   `NXT_DECLINED` instead of trying a later, shorter mount. Intentional and
   documented in the header comment, and pinned by test case 9 — worth one clause
   saying explicitly that a later shorter mount is not tried, nothing more.
2. ~~Dead locals in the caller.~~ **RETRACTED — the finding was wrong.** I read the
   diff hunk, not the whole function: `nxt_cgroup_cpu_limit()` still uses `line` and
   `size` in the `getline` loop that reads `/proc/self/cgroup`, before the mountinfo
   scan. Nothing is dead. Lesson: read the enclosing function, not the hunk, before
   calling a local unused.

## Delta after the merge (head `73d23493`)

The PR merged on a newer master. The delta against the reviewed revision is two
files and no behaviour:

- `src/nxt_lib.c`: the new function's comment is rewritten shorter; "Rust std" is
  dropped from the "Go takes the first such mount too" sentence. No code change.
- `src/test/nxt_cpu_limit_test.c`: the find test loses four cases (the
  prefix-but-not-a-component pair, the reverse mount order, the no-cgroup2 file and
  the empty file) and switches to `fmemopen()` directly on the literal with
  `strlen`, so the copy buffer and the size assertion go. The essential case (the
  first cgroup2 mount does not contain the cgroup, a later one does) stays, the
  too-long case stays, and `nxt_cgroup_relative_path()` keeps its own dedicated
  case table in the same file, so the dropped prefix case is still covered where it
  belongs. The trim is defensible.

The verdict therefore stands for the merged revision: APPROVE, one cosmetic nit,
and the retraction above.

## Unverified

The code comment states that Go and Rust std "also take the first such mount".
Plausible and outside the change's behaviour; not checked here.

## The one line to carry into the release notes

The 1.37.1 entry is present in `CHANGES` and `docs/changes.xml`, both worded to
match the code: "unitd now takes the first cgroup2 mount whose root contains its
cgroup".
