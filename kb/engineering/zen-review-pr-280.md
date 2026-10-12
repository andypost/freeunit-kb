# zen-review PR #280 — router: add an optional bound on an application start

_2026-09-08. Review of freeunitorg/freeunit#280. +2242/−55, 13 files. APPRoved._

## The failure it closes
A worker is forked but never answers PROCESS_READY (e.g. `/bin/sleep` as the app).
It stays alive, so no REMOVE_PID arrives, so the START_PROCESS RPC stays armed for
the life of the router. With `processes: {spare: 0}` that wedges the application
with no way to bound the wait. `start_timeout` is an operator knob to bound it.

## The mechanism (sound)
- New config `application.limits.start_timeout` (seconds), validated like
  `idle_timeout`: not < 0, not > `NXT_INT32_T_MAX / 1000` (msec overflow bound).
  Reaches the router through `NXT_CONF_MAP_MSEC`.
- Deadline timer `nxt_router_start_timer_t` armed on START_PROCESS.
- **Timer-vs-reply race is resolved by construction:** the deadline is driven from
  the payload's completion handler, so a PROCESS_READY landing in the window
  retires the stream (via the normal reply path) before the deadline can fail it.
- Idempotent single-fire: `armed` / `expired` bit flags — the fired timer clears
  `armed` and the error path cannot double-cancel (it checks →armed before
  `nxt_router_start_timer_cancel`). The engine's reference is held while the timer
  node is live (`refs++`).

## Verdict: APPROVE
- Correct bound, precise validation, race resolved through payload completion,
  idempotent. Improves robustness/UX (the failing app is answered 503 rather than
  wedged in `ack_waiting_req`).
- New C test `nxt_router_start_timeout_test.c` + `test_app_start_timeout.py`.
- CI 41 pass / 0 fail. Mergeable/CLEAN.

## Notes
- Sibling: zen-review-pr-289 (start sender auth), pr-291 (MSG_CTRUNC).
- The design comment set is thorough; keep the timer-race reasoning in mind if
  the start path is later touched.
