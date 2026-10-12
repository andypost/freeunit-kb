# zen-review PR #285 — http: handle file truncation in static serving

_2026-09-08. Review of freeunitorg/freeunit#285. Author Andrew Clayton (ac000, F5)._
_Branch `short-read-fix` → master, +5/−0, 1 file (`src/nxt_http_static.c`)._

## What it does
Re-adds a NARROW guard in `nxt_http_static_buf_completion()`: if `pread()`
returns `n == 0` while `rest > 0` (file shrank after `stat(2)` — EOF hit early),
error out instead of looping. It is a fix of the author's OWN earlier commit.

## Context (required for the verdict)
Commit `02d1984c9` ("Remove short read check", Jan 2024) deleted a BROAD check
that fired on any `n != size` and aborted delivery on 9p/network filesystems
(a legitimate short read yields `n > 0`). That removal was correct — but it also
dropped the truncation case: with `n == 0` and `file_pos` not advancing, Unit
spun forever expecting missing bytes.

## Verdict: APPROVE
- ✅ **Does not re-introduce the old bug:** fires ONLY on `n == 0`, not `n != size`.
  Legitimate short read (`n > 0`) still proceeds via `file_pos += n`. This is a
  correct narrowing, not a restore.
- ✅ **Boundary correctness:** `n == 0` with `rest == 0` goes to the `n == rest`
  branch (close/clean); the guard isn't reached. Empty file does not trigger it.
  Only `n == 0` with `rest > 0` (true truncation) errors.
- ✅ **Backward compat:** zero change for normal delivery and network filesystems;
  only hang → error.
- ⚠️ **No test added** (1 file, src only). Black-box test of a mid-send truncation
  is a timing race with no injection point in the delivery path — not
  deterministically testable. Acceptable, documented as `none (timing race)`.

## Notes
- Refs `02d1984c9` (removal of the broad check). Verdict wording: correct narrowing.
