# zen-review PR #288 — router: fail the start RPC when the prototype dies

_2026-09-08. Review of freeunitorg/freeunit#288 (OPEN, `fix/router-proto-death-fails-start`).
_+524/−0, 7 files. Fixes #269._

## The wedge
`nxt_router_start_app_process_handler()` (`src/nxt_router.c:401`) armed an RPC on
the router's own port and sent `START_PROCESS` to the prototype (`:469`), but armed
the registration with **no peer**. The only thing that could retire it was a reply
on its own stream (worker's `PROCESS_READY` forwarded as `NEW_PORT`).

When a prototype dies **after forking the worker and before that worker's READY**,
no reply is possible and nothing retires the registration:
- `REMOVE_PID` carries no stream for a prototype that had itself reached READY
  (`nxt_main_process.c:1200`) → the `RPC_ERROR` branch does not fire;
- `nxt_port_rpc_remove_peer()` (`nxt_port.c:1067`) retires by peer → `no reg found`
  (peer was never set);
- `nxt_port_rpc_close()` runs on the prototype's port, a different table;
- the orphaned worker is reparented to init and exits on a broken-pipe READY.

So `app->pending_processes` keeps the attempt's slot. With `{"spare": 0}` that one
slot is the whole of `max_pending_processes` (`:2061`), so
`nxt_router_app_can_start()` (`:1226`) is false for the router's lifetime. Every
later request joins `ack_waiting_req`; no replacement prototype is ever asked for,
because only the start handler asks and `can_start` gates it.

## The fix
`nxt_port_rpc_ex_set_peer(task, port, app_joint_rpc, dport->pid)` — key the
registration by the prototype's pid so its death retires the RPC. Then
`nxt_port_rpc_remove_peer()` fires `nxt_router_app_port_error()` exactly once
(clears `->peer`, deletes the stream, frees the registration), which decrements
`pending_processes` (`:5073`) and fails `ack_waiting_req` when no process remains.
For a prototype start the peer is the main process — harmless (its death is fatal
anyway).

## Verdict: APPROVE
- ✅ `_ex_set_peer` is idempotent-safe (`if (reg->peer == peer) return`), and on a
  change it first removes the old peer link.
- ✅ `nxt_router_app_port_error` does exactly the slot release: `pending_processes--`
  and fails `ack_waiting_req` when `processes == 0`.
- ✅ Peer for a prototype start = main process, documented as harmless.
- ✅ Single fire, not double: `remove_peer` clears the registration (peer → −1).

## Test (strong)
`nxt_router_proto_death_test.c` (309 lines), sibling of `nxt_router_proto_wedge_test.c`
(which covers the prototype-start branch via `nxt_port_rpc_close()`). Mirrors the
private `nxt_router_app_can_start()` (it is `nxt_inline` and unreachable externally)
with a "must be kept in sync" note. Built like `nxt_router_new_port_test.c`. Added
to `auto/sources`.

## Non-blocking note
The local copy `nxt_router_proto_death_can_start()` duplicates the library predicate
and drifts if `nxt_router_app_can_start()` evolves — same class of drift the keeper
caught on ling. Mark it clearly for sync on every change to `can_start`.

## Notes
- Refs #269. Sibling: zen-review-pr-281 (engine-quit tmcf UAF), pr-282 (compression
  shm leak).
