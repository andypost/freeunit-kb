# zen-review PR #276 — router: close listening socket before ack removal

_2026-09-05. Verified merge review of freeunitorg/freeunit#276. Snapshot of
version, logic, and the honest limitation left behind._

## Fate
- **MERGED** 2026-09-05 20:35 UTC (state=closed, merged=true).
- `src/nxt_router.c` +48/−20, 1 file. Branch `fix/listen-close-ack-order` → master.
- Commit `94553347` is top of origin/master (verified locally + API).
- Co-Authored-By: Claude Opus 5. Codex auto-review: "no major issues".

## What it fixes / logic
Title: "close the listening socket before acknowledging its removal".

**Before (bug):** `nxt_router_listen_socket_close_ready()` — the config
confirmation — ran right after `accept(2)` was disarmed, BEFORE the FD was
actually closed. That reported success ("port free") while the socket was still
bound → a config re-adding the same address hit `EADDRINUSE` at bind time.

**Now (two-phase, split by in-flight):**
- `lev->count > 1` (connections in flight) → ack in **phase 1** (early), because
  drain timing is unpredictable and the config must not wait for idle clients.
- `lev->count == 1` (nothing in flight) → ack in **phase 2**, strictly AFTER
  `nxt_router_listen_socket_release()` (the actual close). `close_ready()` moved
  from before to after the release in `close_finish()`.

**Semantics:** "port free" now honestly means "FD closed" for empty listeners,
and "drain started" for busy ones — not two readings of one cut.

## Verdict
- ✅ Logic correct: ack after close; two-phase split by in-flight; `close_ready`
  in the right branch (phase1 when draining, phase2 after release).
- ✅ Documented: the new comment states WHY the order (ack after release).
- ✅ Removal contract preserved for empty listeners (succ. reconfig = port free).
- ⚠️ **Known limitation (honest, NOT hidden):** for BUSY listeners the FD stays
  bound until drain finishes → re-adding the same address can `EADDRINUSE`
  (retryable). Author flagged as follow-up ("full-drain follow-up"), did NOT
  close it as solved. This is the `ls->count`/`nxt_process_quit()` contract —
  not a bug of this PR.

## Notes
- `test_listeners_port_release` referenced in the comment.
- Related: zen-review-pr-254.md (capget keep-running), zen-review-commit-7311ab.md.
