# zen-review PR #296 — test(python): make the prototype-kill test skip outside its window

_2026-09-08. Review of freeunitorg/freeunit#296. MERGED 2026-09-08 16:51:37 UTC.
_+44/−22, 2 files. Test-robustness follow-up to #288 (which merged before the fix landed)._

## Two real fixes (not cosmetic)
1. **Regex bug in `skip_alert`:** `fr'\b{worker}#{worker} '` → `fr'\b{worker}#\d+ '`.
   The old pattern required pid#pid, which holds only for a main thread on Linux.
   On real Linux, tids != pids, so the skip never matched. Correct: scope by the
   pid (the point of the skip), let the tid be. Sources cite `src/nxt_unit.c:7319`
   and `src/nxt_app_log.c:63` (pid#tid).
2. **Window-entry guard:** before the kill, read `/status` `applications[..][
   processes]['starting']`; if != 1, `pytest.skip`. `starting` is
   `app->pending_processes` (`nxt_router.c:1103`), returned only at worker-port-
   ready, so "inside the window" is now a precondition, not an assertion. A slow
   runner skips instead of reporting a failure the test did not drive.
3. **Bounded fork-wait:** 100→40 iterations + `pytest.skip` instead of
   `assert workers` (protects against "the prototype never forked a worker").
4. **`/status` field confirmed to exist** — `nxt_status.c:44` emits `"starting"`
   serialized from `pending_processes`; the guard reads it correctly.

## Verdict: APPROVE (merged)
- ✅ Real bypassed-skip fix (`\d+`) — genuine, not a flaky-test paper-over.
- ✅ Window guard is a precondition read, correctly scoped to skip.
- ✅ Focus: the test was failing slower runners and pointing at the fix (the
  router change) instead of the runner. Now accurate.

## Notes
- Follow-up to the #288 review comment. #288 itself merged (master head
  `7cda8d6d`), and both #295 and #296 now sit on top of it.
