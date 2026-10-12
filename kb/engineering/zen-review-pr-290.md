# zen-review PR #290 — main: store the state files atomically

_2026-09-08. Review of freeunitorg/freeunit#290. +899/−12, 12 files. Fixes #215.
_APPRoved._

## The bug (data loss)
`nxt_main_file_store` accepted a `tmp_name` but did not use it — wrote into
`file.name` (the LIVE `conf.json`) and called `rename(file.name, name)`, i.e. a
rename onto itself. The short-write path did `nxt_file_delete(file.name)`, i.e.
**deleted the live `conf.json`**. An interrupted store left a truncated config
(or none at all). The controller keeps `conf.json` as its only persistence.

## The fix (textbook atomic write)
- Write into `tmp_name` (a sibling transient in `dir`, beside the destination).
- `nxt_file_sync(task, &file)` (fsync) BEFORE the rename — so the rename doesn't
  become visible with incomplete contents.
- `nxt_file_rename(tmp_name, name)` — atomic replacement.
- `nxt_file_dir_sync(task, dir)` AFTER the rename — without it the rename may not
  survive a power loss. `EINVAL`/`EOPNOTSUPP` tolerated as not-a-store-failure
  (the rename has already happened; only a directory-refusing fsync).
- Every failure BEFORE the rename: `nxt_file_delete(tmp_name)`, live `name` intact.
- `nxt_file_inherit` carries mode/ownership from the transient to the target.

## Verdict: APPROVE (unchanged after growth)
- Correct, textbook atomic-write ordering. Fixes the real data-loss (#215).
- Known trade-off, documented: a `name` that was a symlink is replaced by a
  regular file (the price of atomicity); a symlinked state *directory* still
  resolves. Honest.

## New test coverage (the growth)
- `test_state_store.py`: puts the state dir on a 64 KiB tmpfs (needs root +
  CAP_SYS_ADMIN in a --privileged container, plus --restart; skips otherwise) and
  asserts a config too large for the filesystem leaves the ORIGINAL conf.json
  intact (observes the short-write unlink on the unfixed code). Well-targeted.
- `nxt_main_file_store_test.c` (C unit test), `test/syscalls/capture.sh` +
  baseline drift additions (open/fsync/rename now in the syscall set).

## Notes
- Fixes #215. The `file_store` core is bytes-identical to the reviewed
  (+644) version; the delta is test-only (421-line C test + 141-line pytest).
- Sibling: zen-review-pr-301 (discovery JSON), pr-299 (close-before-ack).
