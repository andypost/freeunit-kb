# #663 / #662 decisions — the libunit wake-up that can block at quit (with #654/#597 status)

_2026-10-11. Read at `origin/master 4fef769d` (`src/nxt_unit.c` searched through `git show`, never the stale worktree — a first pass searched the checkout and wrongly concluded the merged #661 functions did not exist). Evidence below is code at that SHA plus live API measurement._

## #663 — root cause confirmed, one fix recommended

Chain at master: `nxt_unit_ctx_free_rbufs()` → for each segment list, the buffers another context parked behind this one go to `nxt_unit_unpark_rbufs(&ctx_impl->ctx, &others)` → per buffer it takes the `port != NULL` branch (5566-5569) and calls `nxt_unit_awake_port(ctx, port)` → `nxt_unit_port_send(ctx, port, &msg, sizeof(msg), NULL)` at **5622-5641**. The message is `_NXT_PORT_MSG_RPC_READY` (stream 0).

Why it blocks: `nxt_unit_sendmsg()` retries only on `EINTR`; there is **no `MSG_DONTWAIT` anywhere in `src/nxt_unit.c`**, and the port is put in blocking mode at `nxt_unit_init()` (`nxt_unit_fd_blocking(read_port.in_fd)`). `nxt_unit_port_send()` may also route the wake-up through the target's app queue first: `nxt_port_queue_send()` returns a `notify` flag and **on overflow returns -1 with an alert and no retry** (the issue's claim is accurate) — when `notify` is 1 the `_NXT_PORT_MSG_READ_QUEUE` marker is written to the socket, and that write is the one that can block.

**Decision: option 2, minimal form — make the wake-up non-blocking and treat `EAGAIN`/`EWOULDBLOCK` as "not needed", not as an error.**

The guarantee that makes dropping safe (the issue says to establish this first, and it holds): this is a datagram socket, so a full **send** buffer means unread datagrams sit in the target's receive queue ⇒ the target's `poll(read_port->in_fd)` returns immediately ⇒ it will run and drain `pending_rbuf`/the app queue without the nudge. `EAGAIN` is therefore *evidence the peer is already wake-able*, not a lost wake-up. A retry-with-deadline (the rest of option 2) adds nothing: if the peer stays unreadable the deadline only delays the same drop, and the free path is not the place to wait.

- **Reject option 1 as written** ("drop silently"): same behaviour, but a dropped wake-up must be visible — log at debug with the target port id, so a future hang is diagnosable.
- **Reject option 3** (close the read descriptor before the hand-back): the target read port belongs to a **live** other context; the freeing context may not close it. It also does not bound the wait for the *sending* thread.
- Keep #661's `nxt_unit_port_use()`/`release()` pair — it protects object lifetime and is orthogonal.

Implementation sketch (contained to `src/nxt_unit.c`): add a flags parameter to the internal `nxt_unit_sendmsg()`/`nxt_unit_port_send()` (18 call sites can stay unchanged if `nxt_unit_port_send()` keeps its signature and forwards `flags = 0` to a new static `nxt_unit_port_send_flags()`); in `nxt_unit_sendmsg()` return a distinct value for `(flags & MSG_DONTWAIT) && (err == EAGAIN || err == EWOULDBLOCK)` and log it; `nxt_unit_awake_port()` passes `MSG_DONTWAIT`. `EINTR` keeps its retry.

## #662 — the test design is sound; it needs one correction and one addition

Verified at `4fef769d`: `nxt_unit_take_awaiting_rbufs()` (5584) does `nxt_atomic_fetch_add(&rbuf->ctx_impl->unparking, 1)` before the queue move, `nxt_unit_ctx_free_rbufs()` spins on `while (ctx_impl->unparking != 0) nxt_thread_yield();`, and `unparking` is initialised at 880 — so the hook point the issue names is real and the counter is 1:1 as described. The hook must sit **before** the increment, inside the window where the buffer is off the segment list and not yet counted.

Two additions to the plan:

1. **A second, race-free test for #663** that does not need the hook or any interleaving: shrink the sender's `SO_SNDBUF` on the target's socket, have the target stop reading, fill the socket until `sendmsg` returns `EAGAIN` **in the test itself** (so the full state is established deterministically, no sleeps), then free the context and assert `nxt_unit_ctx_free()` returns. On pre-change code this is the hang; on the fix it returns. This is the test that pins #663's contract, and it is immune to scheduling.
2. The #662 test's step 3 ("assert the free does not return while the helper is stopped") needs a bounded wait — assert over a short deadline rather than a bare `assert` on a blocking call, otherwise a regression turns the suite into a hang instead of a failure (the same class of problem #641 just fixed for the websocket client).

`check-test-hooks.sh` already enforces that a `#if (NXT_TESTS)` hook in `src/nxt_unit.c` reaches only the test programs, so the new hook needs no gate work.

## #654 — the measured numbers reproduce; two corrections

Live check (2026-10-11, Actions API):

- A pull-request `Build & Test` run has **19 jobs** ✔ (matches the issue) and took **616 s ≈ 10.3 min** (issue: 9–12 min ✔). The three longest legs are `test (python-3.13)` 8.8 min, `test (python-3.14)` 5.9, `test (python-3.12)` 5.0 — the python legs are the critical path ✔.
- A **master push** run has **32 jobs** ✔.
- Correction to add: the python-3.13 leg at 8.8 min is above the issue's named 6.7 min, so the "target ~8 min" wall time is already exceeded by a single leg — the shard order matters more than the job count now.
- The named sleeping tests in #402 are still the residual: the fix is test-side (drop the sleeps), not CI-side.

## #597 — status of the wave-0 items, plus a finding on #638

- #595 → fixed by #598 (merged 2026-10-07) ✔; #641 (websocket client timeout) merged 2026-10-10 ✔; #573 merged ✔; `2e334334` (no `epoll_ctl MOD` per drain) is in master ✔.
- Still open and decidable only with a rerun: the Alpine s390x `test_asgi_websockets_*_over_buffer_limit` hang — #641 turns the hang into a failure, so the **rerun decides** big-endian product bug vs test race. That rerun needs qemu s390x and is the one item I cannot do from here.
- **#638 (branch `perf/libunit-message-cost`) is currently RED**: `test (java-25)` fails in the step "Run java tests" (run 38135575288, 2026-10-11 11:26Z). Issue #11 says only "needs a fresh review of the new code" — the live state is stronger: the head (`56b54721`, +1819/−162, UNSTABLE) fails a test leg, and the java failure is not mentioned anywhere. That is the first thing to triage on that PR, ahead of the review.

## What I had to correct in my own process

- **Read code through `git show <ref>:<path>`, not the working tree.** The checkout was days behind; grepping it produced a false "the merged functions do not exist" conclusion about #662's hook point. Fetch, then read the ref.
- My GitHub identity is read-only on the org (**403** on issue PATCH, both `freeunit-exp` and `freeunit`; `git push --dry-run` has no credential). So the agent's issues can be analysed and answered here, but not commented on: the drafts have to be posted by the maintainer, or the token needs `issues: write` + `pull_requests: write`.

## Result — the fix is pushed as a fork PR (2026-10-11)

- Branch `hermes/libunit-wakeup-nonblock`, commit `bdda389d`, **PR #25 in `freeunitorg/freeunit-exp`** (+52/−12 in 4 files: `src/nxt_unit.c`, `src/nxt_socket_msg.{c,h}`, `src/nxt_socketpair.c`, plus 3 call sites in `src/test/nxt_port_ctrunc_test.c`).
- **Local build is impossible here**: no C compiler (`cc not found`) and no root (`id` = uid 1000, no `sudo`, `apk` present but unusable) — reported instead of shipping an untested patch. Fork CI is the evidence: `c-tests` PASS, `c-tests-almalinux8` PASS, `c-tests-macos` PASS, `c-tests-pcre1` PASS, **`hardening-strict-fedora` gcc + clang PASS** (so the `EAGAIN` handling is warning-clean under strict hardening); `core` and `c-tests-asan` were still pending at hand-off.
- Change shape: `nxt_sendmsg()` gained a `flags` argument reaching `sendmsg(2)` (existing callers pass 0); `nxt_unit_port_send()` stayed a wrapper over the new `nxt_unit_port_send_flags()` so its 18 call sites are untouched; `nxt_unit_awake_port()` is the only `MSG_DONTWAIT` caller; `EAGAIN` under `MSG_DONTWAIT` → debug line + return 0; `EINTR` keeps its retry.

**Load-bearing finding for the maintainer — the fork's upstream sync is broken.** `main` has diverged: **12 commits behind, 4 ahead** of upstream (`findings: T1/T2`, `hermes: operating rules`, `ci: daily upstream fast-forward`), so a fast-forward is impossible, and `POST /repos/freeunitorg/freeunit-exp/merge-upstream` answers **422 "Repository rule violations found"** (a ruleset on `main`). Consequences: the daily sync job cannot be doing what its name says, and any `hermes/*` branch based on `main` misses merged upstream code (it misses #661 entirely). Fix options: let the App bypass the ruleset for `merge-upstream`, or rebase the 4 fork commits onto upstream. The PR is based on upstream `4fef769d` and can be rebased once `main` is synced.

Channel activity: two comments posted on freeunit-exp **#11** from the `freeunit-agent` App identity (the analysis, then the PR + CI result). The other side posts as `andypost` ("Claude session here, works upstream for the maintainer"), so posts are signed "Hermes side (SOUL)" to keep the two apart.

## Related

- `engineering/freeunit-satellite-repos-2026-10.md` — the channel these issues arrive through
- `releases/1.37.1-plan.md` — the release the wave-0 items belong to
