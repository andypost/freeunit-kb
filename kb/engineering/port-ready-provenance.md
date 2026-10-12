# Plan: #231 behavioural half — a queueless port must fail the start, not wedge the worker

Status: 2026-08-29, post-release master work (origin/master @ d8feac33; no relevant files changed since 9f458653). The "now" half of
#231 (log/comment rewording) is merged (#232).
Review history: opus plan agent; local codex (gpt-5.6-sol, high) review folded in — it corrected the provenance gate, the kill target, the
SIGCHLD path and the main-process part. All anchors on origin/master; the ones in the issue text have drifted.

## 0. The deferral reason is stale

#231 / e8b7f644 deferred the behavioural fix "pending sender provenance" for `PROCESS_READY`. Provenance already exists and is in use:

- `nxt_recv_msg_cmsg_pid()` — `src/nxt_port.h:239` (`cmsg_pid` `:227`, `NXT_USE_CMSG_PID` `:217`: Linux ucred **or** FreeBSD cmsgcred).
  Filled on both recv paths (`src/nxt_port_socket.c:816-825`, `:1015-1021`).
- Linux: `SO_PASSCRED` on both ends of every socketpair (`src/nxt_socketpair.c:49-65`; libunit `src/nxt_unit.c:5559-5572`).
  FreeBSD: `nxt_socket_msg_oob_init()` attaches an `SCM_CREDS` cmsg on every send (`src/nxt_socket_msg.h:86-108`), and
  `nxt_unit_ready()` goes through it (`src/nxt_unit.c:1044-1062`); receiver reads `cmcred_pid` (`:209-228`). → gate on
  `NXT_USE_CMSG_PID`, **not** `NXT_HAVE_UCRED`. (Source path complete; not executed on FreeBSD.)
- Used by ~10 privileged handlers: `src/nxt_main_process.c:482,665,776,1212,1444,1571,1757,1885`, `src/nxt_cert.c:1365`,
  `src/nxt_script.c:663`, `src/nxt_application.c:762`.
- The ACL TODO at `src/nxt_port.c:239-254` cites the stale blocker ("SCM_CREDENTIALS not consistently available") — update it.

### Which pid is the receiver-visible one (codex correction — this decides both the gate and the kill target)
`nxt_process_t.isolated_pid` (`src/nxt_process.h:129`) is always the pid **as seen by the process that forked it**: set at fork
(`src/nxt_process.c:337`, `:679`), left alone by `nxt_process_whoami_ok()` (`:902-910`), while `process->pid` is rewritten to the
global pid on PROCESS_CREATED (`src/nxt_application.c:762-777` — which already matches `cmsg_pid` against `isolated_pid`), and the
prototype's SIGCHLD also looks children up by `isolated_pid` (`src/nxt_application.c:841-865`, hash `:1232-1241`).

| receiver ← process | `process->pid` | `process->isolated_pid` | `cmsg_pid` |
|---|---|---|---|
| main ← prototype/core child | global | == global | global |
| non-isolated prototype ← worker | global == local | same | same |
| pid-isolated prototype ← worker | global | **local** | **local** |

Therefore the credential must equal **`isolated_pid` only**. The earlier "accept either" is a bypass: in a pid namespace another task
whose ns-local pid numerically equals the victim's global `process->pid` passes; a compromised worker can fork toward such a collision.

## 1. Mechanism (re-anchored)

| claim | anchor |
|---|---|
| READ_SOCKET marker only under `port->queue != NULL` | `src/nxt_port_socket.c:221`, `:257` |
| libunit delivers socket msgs only when `from_socket > 0`; counter only from a dequeued marker | `src/nxt_unit.c:6459`; `:6416`, `:4905` |
| suspend; second → `"too many port socket messages"` | `src/nxt_unit.c:6469-6486`, `:6480` |
| native receiver same gate | `src/nxt_port_socket.c:747`, `:924`, `:1073` |
| libunit refuses a queueless NEW_PORT itself | `src/nxt_unit.c:1315-1324` |
| site 1: `nxt_port_process_ready_handler()` — installed in the **prototype** (`src/nxt_application.c:112-121`) | `src/nxt_port.c:460`; mmap `:523`; failure arm `:551-587`; `queue == NULL` case `:577`; READY set `:516`; broadcast `:596` |
| site 2: `nxt_main_new_port_handler()` | `src/nxt_main_process.c:415-455`; mmap `:428`; alert `:442` |
| broadcast forwards `queue_fd == -1`; skips the named process itself and self | `src/nxt_port.c:303-355`; skip `:312-316` |
| main already holds the worker port from WHOAMI before NEW_PORT arrives | `src/nxt_main_process.c:776-799` |
| router twin (#223) | `src/nxt_router.c:693`, `:735`, deferral `:738-757`, bare return `:761-763` |

Corrections to the issue text (read-verified, not runtime-confirmed):
- Site 1 runs in the **prototype**, not main: libunit's READY goes to `proto_port->pair[1]` (`src/nxt_application.c:1202-1207`;
  exec'd apps via `src/nxt_external.c:113-125`). Main hits the bug through site 2 — exactly the PR #212 repro.
- Forgery is real: port sockets are per-owner, `pair[1]` is duplicated to every peer, `msg->port->pid == nxt_pid` always
  (`src/nxt_port.c:227-236`, `src/nxt_runtime.c:1914-1918`); `nxt_port_handler()` (`:257`) dispatches on wire `type` only. Any worker
  can forge a READY naming a sibling and **re-point the sibling's `port->queue` at attacker shm** (`src/nxt_port.c:530-549`). Embedded
  modules also keep main's `pair[1]` (`nxt_proc_keep_matrix[APP][MAIN]`, `src/nxt_process.c:77-83`, `:369-386`).

## 2. Options considered

- **(B) fail unconditionally** — rejected: kill-any-start primitive for any worker; a silent refusal is #214-class — the RPC never
  completes, `pending_processes` stays 1, with default `processes: 1` (`src/nxt_router.c:2057-2061`) the app never starts again.
- **(C) mark READY then kill** — rejected, but for a corrected reason: the worker's parent is the prototype, whose
  `nxt_proto_sigchld_handler()` (`src/nxt_application.c:825-921`) sends REMOVE_PID whenever state ≠ CREATING (`:907-909`) and never
  clears `stream` on READY (the `src/nxt_main_process.c:1108-1110` clearing cited before is main's handler — wrong site). The
  zero-delay respawn loop happens only if the bad port was **broadcast and installed in the router**: `nxt_router_app_port_close()`
  restarts at `src/nxt_router.c:5390-5409` with no backoff. So: not-READY + no-broadcast is what prevents the loop; READY itself is
  merely wrong state.
- **(A) authenticate, then fail the start via the existing REMOVE_PID→RPC_ERROR path** — chosen.

## 3. Work, staged

### PR 1 (S) — authenticate PROCESS_READY   [standalone security fix; merge first]
`src/nxt_port.c` after the process lookup at `:481`:
```c
#if (NXT_USE_CMSG_PID)
    if (nxt_slow_path(nxt_recv_msg_cmsg_pid(msg) != process->isolated_pid)) {
        nxt_alert(task, "process %PI sent PROCESS_READY claiming process %PI",
                  nxt_recv_msg_cmsg_pid(msg), msg->port_msg.pid);
        nxt_port_recv_msg_close_fds(msg);
        return;
    }
#endif
```
- `isolated_pid` only (§0 table). Tighten the repeated-READY concession at `:483-497` (same sender: still tolerated).
- Update the TODO at `:239-254`.
- Tests in `src/test/nxt_port_ready_test.c` (fixture builds runtime/process/port by hand, `:407-455`): **every existing known-process
  case must now set `msg.cmsg_pid = process->isolated_pid`** or it is rejected on ucred builds. New: foreign `cmsg_pid` → rejected, fds
  closed, state untouched; model `rt->is_pid_isolated` with `pid != isolated_pid` and assert `cmsg_pid == isolated_pid` passes and
  `cmsg_pid == pid` is **rejected**.
- Commit message: non-ucred/non-cmsgcred platforms (macOS/NetBSD/OpenBSD/illumos) stay unauthenticated — same as every sibling gate.
- Pre-landing check (still open): the TODO's "dispatch runs before the prototype's process registration completes" — confirm the
  missing-process path at `:481` already drops READY for an unregistered process (it does today; the gate runs after it).

### PR 2 (M) — fail the start on a refused queue   [closes #231; site 1 only]
`src/nxt_port.c` else-arm `:551`, `port->queue == NULL` case only (`:577`):
1. Do not set READY — move the assignment at `:516` below the mmap (guard order at `:498-509` says why).
2. Skip `nxt_port_send_new_port()` at `:596` — never broadcast an unreachable port.
3. **`kill(process->isolated_pid, SIGKILL)`** — the receiver-visible pid (§0; `process->pid` is the global pid and would hit ESRCH or a
   *different* process inside a pid namespace). SIGKILL, not SIGTERM: the worker has served nothing yet, and a compromised worker can
   ignore SIGTERM, leaving the RPC and `pending_processes` pending forever with no escalation. Log a failed `kill()` (ESRCH can be a
   legitimately already-pending SIGCHLD). Precedent `src/nxt_process.c:696-703` uses the fork-returned pid — same identity rule.
   A port QUIT cannot work, by #231's own premise.
Then existing plumbing fails the start (traced by codex, no leak/double-free found): descriptor closed once by
`nxt_port_recv_msg_close_fds` (`src/nxt_port.c:551-594`, `src/nxt_port.h:247-268`) → prototype SIGCHLD finds the child by
`isolated_pid`, sends REMOVE_PID (state CREATED ≠ CREATING, `src/nxt_application.c:841-915`) with the start stream
(`src/nxt_port.c:802-842`), closes its ports → main closes its WHOAMI copy via `nxt_port_remove_pid_handler()` (`src/nxt_port.c:864-895`)
→ router: no peer to cancel (start RPC `src/nxt_router.c:458-479` never calls `nxt_port_rpc_ex_set_peer()`), stream ≠ 0 → RPC_ERROR
(`:1111-1132`) → `nxt_port_rpc.c:361-417` deletes the registration once → `nxt_router_app_port_error()` `:5054` →
`nxt_router_app_start_failed()` `:5092-5104` decrements `pending_processes`. The router never held the port (no broadcast). Later starts
are request-driven (`src/nxt_router.c:5637-5669`) — same as a worker crashing at startup; no autonomous loop. Say so in the commit
message rather than adding backoff.

**Site 2 (`nxt_main_new_port_handler`) — explicitly NOT in PR 2.** Closing/dropping main's copy does not fail the start: by the time
NEW_PORT reaches main the prototype has already marked the worker READY and broadcast it, the router may be serving from it, and main
already owns the port from WHOAMI (`src/nxt_main_process.c:776-799`; base handler `src/nxt_port.c:383-420` keeps the queue fd). Dropping
it turns "eventually wedges libunit" into "silently misses CHANGE_FILE/QUIT from main" — the SIGUSR1 acceptance would fail. And NEW_PORT
has no provenance check, so a forged short-queue NEW_PORT from an embedded worker would trigger the destructive path. Keep the alert
(#232) and fold the real fix into PR 3 (#223), which owns NEW_PORT provenance + validate-before-commit for router **and** main.
If a stopgap is wanted: the mechanically safe removal is `nxt_port_close()` (`src/nxt_port.c:154-190`) + `nxt_runtime_port_remove()`
(`src/nxt_runtime.c:2066-2085`) — but only behind a prototype-sender gate, and it still needs a policy to report the worker.

Tests (PR 2):
- Trigger: `nxt_port_queue_mmap()` (`src/nxt_port.c:51-86`) returns NULL on a short descriptor (`:69`) — same branch as MAP_FAILED;
  `nxt_port_ready_test_short_queue()` already feeds a one-page memfd (Linux-only, `NXT_HAVE_MEMFD_CREATE`, `:99-329`).
- "No broadcast" needs a real observer: `nxt_port_send_new_port()` skips the named process and self (`:312-316`), so the current
  single-process fixture passes vacuously. Add a second registered process with a real socketpair and assert it receives nothing, or
  an `NXT_TESTS` broadcast counter hook (pattern: `nxt_port_test_*` in `src/nxt_port.h:389-391`, `src/nxt_port_socket.c:40-70`).
- Kill target: never `nxt_pid + N`. Fork a sleeper child, set `isolated_pid` to it, `waitpid()` it after the handler; or a
  `NXT_TESTS` kill hook.
- Assert: state ≠ READY, descriptor closed, kill delivered, no NEW_PORT observed.
- Soak: `src/test/nxt_router_start_fail_soak_test.c` injects before/while START_PROCESS and uses `nxt_port_rpc_close()`
  (`:187-249`, `:267-299`) — different route. New soak must deliver a last-marked REMOVE_PID carrying the registered start stream through
  `nxt_router_remove_pid_handler()` 1000× and assert `pending_processes` returns to baseline.
- Python (regression only; cannot trigger a refused queue): 503 + `skip_alert` shape (`test/test_python_application.py:556-561`), plus
  positive guards that SIGUSR1 rotation and reconfig still reach workers. Working-tree `test/test_process_*.py` are older than
  origin/master — read origin first. s390x control run on pro4s-4 (test touches queue layout).

### PR 3 (L) — #223: NEW_PORT provenance + validate-before-commit (router **and** main)
`nxt_port_new_port_handler()` (`src/nxt_port.c:360-456`) has no provenance check and `/* TODO check b size */` at `:378`; router side
`src/nxt_router.c:738-757` cannot tell a fresh port from a live one; main side is §3/PR 2's excluded site 2. Separate plan.

## 4. Sequencing / review
PR 1 → PR 2 → PR 3, never folded. Each: opus implements in a worktree (no git state changes in the shared checkout; harness
skills/tools for build/test; ast-grep sweep "PROCESS_*/NEW_PORT handler without `nxt_recv_msg_cmsg_pid`" — verify empty results),
Fable/opus adversarial review, local `codex review --uncommitted`, then re-run `./configure`.

## 5. Acceptance (PR 2)
- [ ] Worker whose queue is refused never becomes READY, is never broadcast, is killed by its receiver-visible pid; router logs a start
      failure and serves 503 until the next request-driven start.
- [ ] `pending_processes` returns to baseline (soak through `nxt_router_remove_pid_handler`).
- [ ] SIGUSR1 + reconfig reach healthy workers (regression).
- [ ] Log-rotation repro from PR #212 (`too many port socket messages`) cannot occur via site 1; site 2 remains documented as #223 scope.
