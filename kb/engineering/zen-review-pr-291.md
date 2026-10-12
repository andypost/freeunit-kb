# zen-review PR #291 — socket: refuse a port message whose control data was truncated

_2026-09-08. Review of freeunitorg/freeunit#291. +1115/−14, 9 files. Fixes #264._
_APPRoved. Cross-language (Linux C + Go binding)._

## The bug
`recvmsg()` under `RLIMIT_NOFILE` sets `MSG_CTRUNC`; the `SCM_RIGHTS` block is cut.
What a handler then sees is a well-formed, kernel-authenticated message whose
descriptor is `-1`, so every fd-typed message (NEW_PORT, MMAP, port hand-off)
takes its fd-less path — a silent, hard-to-infer corruption (payload and
credential intact, only SCM_RIGHTS cut).

## The fix (correct, cross-language)
- `nxt_socket_msg.h`: carry `oob->truncated = (msg.msg_flags & MSG_CTRUNC) != 0`,
  with `nxt_recvmsg` clearing `msg.msg_flags = 0` first so it reads what
  `recvmsg()` wrote.
- `nxt_socket_msg_oob_get_fds`: refuse when `oob->size == 0 && oob->truncated`.
- `nxt_unit_ctx_port_recv` (C) and `nxt_unit_ctx_port_recv` (Go) drop the message
  with a distinct alert naming type/stream, closing any fd that did arrive
  (`closeUnixRights` in Go, `done:` path in C). Go detects `MSG_CTRUNC` at the
  syscall level because `ReadMsgUnix` consumes it.
- `nxt_socket_msg_oob_reset` / `nxt_port_read_handler` unwind the counter.
- New C test `nxt_port_ctrunc_test.c`.

## Refined verdict on the Codex P1
Codex P1: the refusal branch does a single `nitems--` + `return`; if a queue-only
message was enqueued after the READ_SOCKET marker but before the truncated
datagram was processed, its sender saw `nitems != 0` and wrote no wakeup, so the
branch leaves a queued message with `nitems > 0` and no reader scheduled → port
stalls. Mechanism is coherent with the `nxt_port_queue_send` notify protocol
(`notify = (i == 0)`, pre-increment).

**Assessment (traced the nitems accounting):**
- The reader already has the canonical **decrement-and-recheck handoff** that
  Codex asks for at `nxt_port_socket.c:959-966` (`nitems--`, re-recv, `return` if
  still empty, else `nitems++`). The truncation branch (`:1091`) does a *plain*
  `nitems-- + return`, diverging from that established pattern — so the concern
  is NOT baseless: it's a real divergence from the file's own recheck-handoff.
- Trigger is rare (truncation + a concurrent queue-only enqueue in the same
  window). The pre-fix code was strictly worse (bare `return` stranded the buffer,
  the marker and the entry-hold on EVERY truncation).
- **Verdict: not a merge blocker; a valid low-probability P1 worth a follow-up.**
  Remedy: reuse the `959-966` recheck-handoff on the truncation path (or keep
  draining), plus a targeted test forcing truncation + concurrent enqueue. Not
  lost, documented.

## Notes
- Fixes #264. Cross-language (Linux SCM_CREDENTIALS + Go binding). Sibling:
  zen-review-pr-289 (sender auth), pr-280 (start_timeout).
