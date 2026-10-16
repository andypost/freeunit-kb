# Port-message trust model (why #341 is hardening, not a release blocker)

**Date:** 2026-09-17, updated **2026-09-28** · **Status:** read from `origin/master`
(tip `d4c8558f`, 2026-09-28) · **Trigger:** Andrey — "#341 очень сомнительный блокер".

## UPDATE 2026-09-28 — the fix landed on master (unshipped)

The router's sender gate is implemented, in three merged steps plus a follow-up,
all after the `1.36.1` tag (no tag contains them; `version` still says 1.36.1):

1. `router: accept control messages only from main and the controller`
   (PR **#506**, merged 2026-09-27) — gates seven control types on the router
   main port: `QUIT`, `CHANGE_FILE`, `ACCESS_LOG` → main; `REMOVE_PID` → main or a
   registered prototype; `DATA`, `APP_RESTART`, `STATUS` → the controller. A refused
   message gets one alert and its descriptors are closed; no reply is sent, because
   the sender chooses the reply port and stream. The commit itself states the limit:
   the gate "makes the attack harder, but does not stop it yet", because `NEW_PORT`
   sets `rt->port_by_type[]` for the type *in the message* — an application could
   announce itself as MAIN and then send `QUIT`.
2. `router: put the sender gate of the main port in one table` — one table
   `nxt_router_gates[]`, every gated type routed through `nxt_router_gate_handler()`
   + `nxt_router_msg_sender_ok()`; a type with no row has no sender that passes.
3. `router: check the sender of NEW_PORT, RPC replies and the libunit requests` —
   closes the `NEW_PORT` hole and gates six more types: `NEW_PORT` (main; a
   registered prototype only for an application port; an application only for its
   own application port with stream 0), `RPC_READY`/`RPC_ERROR` (`NOT_APP`),
   `GET_PORT` (`SELF`, and the requested port must be a router port), `GET_MMAP`
   (`SELF`, reply port must be an application port — replaces an `nxt_assert()`),
   `MMAP`/`OOSM` (`SELF`). It also fixed a short `NEW_PORT` body that took its
   missing bytes from an earlier message in the same buffer.
4. `router: refuse GET_PORT for a foreign pid when the port is not in the hash` —
   closes a bypass where an unhashed foreign port id passed the check.

The router's handler table now points every type at `nxt_router_gate_handler`
except `.detached`, which keeps `nxt_router_detached_handler`.

**Still open, stated by the commits themselves:** `nxt_port_rpc_handler()` does not
compare the sender against the peer of the registration, so main, the controller or
any prototype can answer any stream of the router (needs a change in the shared RPC
code); the router *engine* ports stay open because their messages can arrive over the
shared-memory queue, which carries no pid; `DETACHED` is not gated; on platforms
without sender credentials the check falls back to the pid in the header, so it is
weaker there; and the dispatcher-level per-type ACL in the `TODO(audit-V5-medium)`
block of `src/nxt_port.c` is still not done (blocked on process-registration
ordering — dispatch can run before a prototype has registered a child).

**Issue hygiene:** #341 itself is untouched — open, zero comments, last updated
2026-09-13, and no PR is linked to it. It should be closed (or annotated) when the
next release actually ships the series; until then, shipping behaviour is still
1.36.1, so the public wording must say "gated on master, unshipped".

## The mechanism was real (as read 2026-09-17, before the fix)

- The router dispatches port messages on the sender-chosen type byte:
  `nxt_port_handler()` takes `handlers = msg->port->data` and calls
  `handlers[msg->port_msg.type]`, with no sender check of its own.
- The router's own table (`nxt_router_process_port_handlers`) is ungated: `quit`,
  `rpc_ready`/`rpc_error`, `app_restart`, `status`, `remove_pid`, `access_log`,
  `new_port`, `get_port`, `change_file`, `mmap`, `get_mmap`, `data`, `oosm`.
- An application worker holds the write end of the router's main port
  (`router_port->pair[1]` handed to the worker in `nxt_application.c`), so it can
  `sendmsg()` any type directly instead of going through libunit.

## Why it is a weak RELEASE blocker

1. **Not a regression.** The gap predates this cycle; nothing in the 1.37.0 delta
   creates or widens it. A release gate exists to catch what the cycle changes.
2. **Reachability needs code execution inside an application worker.** In Unit's
   own trust model the application *is* the operator's code, and the isolation
   feature is containment of that application, not authentication of the router
   against it. For a single-owner deployment it is not an escalation past
   "the application is compromised".
3. **The tree already carries the plan and the partial fix.** `src/nxt_port.c`
   documents it as `TODO(audit-V5-medium)`: sender-type ACL for privileged port
   messages, gated handler-by-handler on `nxt_recv_msg_cmsg_pid()`. Already gated:
   main's `PROCESS_CREATED`/`START_PROCESS`/`PROCESS_READY`, the prototype's
   equivalents, and the cert/script/socket/access-log handlers. What is left is
   the router's table plus the generic dispatcher ACL.
4. **The earlier ACL draft was reverted for a concrete reason**, not by neglect:
   the kernel-validated sender pid was not available on the existing socketpair.
   That blocker is gone (`nxt_socketpair_create()` now sets `SO_PASSCRED`), and
   what remains is a design question — the ACL cannot require an already-registered
   sender, because dispatch can run before the prototype has registered a child.
   So the right next step is a decision, not another patch.
5. **One severity claim in the issue is overstated.** `#341` says a forged `QUIT`
   "ends service for every application behind that router — instant, not gradual".
   The router declares `.restart = 1`, so main re-forks it immediately and without
   backoff: the result is one router-wide teardown — every application and
   connection behind that router drops, the sender included — not a permanent kill.
   A sustained loop is self-limiting, though other types (`status`, `app_restart`,
   `remove_pid`, `access_log`) do not kill the sender.
6. **Platform note:** on macOS, NetBSD, OpenBSD and illumos there is neither
   `SCM_CREDENTIALS` nor `SCM_CREDS`, so those platforms stay unauthenticated by
   construction — relevant only if a non-Linux deployment is in scope.

## Why it is NOT a dubious CLAIM limiter

Two consequences sit exactly on the multi-tenant / isolation story:

- `QUIT` → one compromised application worker drops **every** site behind that
  router (cross-tenant availability).
- `rpc_ready`/`rpc_error` → `nxt_port_rpc_handler` accepts an application-supplied
  descriptor, and the TLS path would adopt it as a chain file. That is a
  cross-boundary descriptor, not merely a DoS.

## Wording to use publicly

Not "applications can send unauthenticated port messages" (sounds like a remote
hole), but: **sender validation on the router's port table is not done yet; it
requires an already-compromised application worker, and isolation is containment
of an application, not protection against one.** Class: hardening /
defense-in-depth, tracked, with the design step named.

## Related

- `releases/1.37.0-in-flight-classification.md` — the actual pre-tag checklist.
