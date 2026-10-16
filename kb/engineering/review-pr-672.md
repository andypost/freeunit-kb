---
title: Review — FreeUnit PR 672 (a claimed request that is never acknowledged)
description: Verdict APPROVE for the claim/ack timeout fix; one release blocker (no changelog entry) and two nits.
tags: [review, router, libunit, rpc, pr-672]
status: final
---

# Review: PR 672 — router, libunit: answer a claimed request that is never acknowledged

Head judged: `0b793e81` (3 commits). Base `origin/master` `678ef06d`.
Diff: 7 files, +787/−72 (about 180 lines of production code, the rest tests).
Verdict: **APPROVE on the code**, with one release blocker and two nits.

## What it does

A request that a worker claimed from the shared queue and never acknowledged was
left unanswered for ever: the deadline returned early, the 503 path was skipped, and
the router could not tell which worker held it. Now:

1. the first expiry of the app deadline logs an alert and re-arms the timer;
2. the second expiry logs a warning and falls through to the normal 503-and-unlink;
3. libunit tells the router when a request fails before its acknowledgement, so the
   router is not left waiting for the deadline at all;
4. the request's reply port is removed from the port hash when it cannot be reached,
   so a later request does not wait for a `NEW_PORT` that was never asked for.

## Code verdict (what was checked)

- **One `RPC_ERROR` per failed request, not two.** The new notification in
  `nxt_unit_process_msg` sits on the mmap-read failure branch only
  (`rc != NXT_UNIT_OK && rc != NXT_UNIT_AGAIN` for a `REQ_HEADERS` message); the
  `fail:` label inside `nxt_unit_process_req_headers()` covers malformed content
  after a *successful* read. The two paths are disjoint, so a request cannot be
  reported twice.
- **`claimed_expired` starts at zero.** The RPC data lives in the extension of
  `nxt_port_rpc_reg_t`, allocated with `nxt_mp_zalloc` (`src/nxt_port_rpc.c:240`)
  — zeroed, so the first expiry is always the alert/re-arm one. (Worth noting,
  because the same PR had to set `req->response_port = NULL` explicitly where the
  libunit request-info pool does *not* zero.)
- **Descriptors are safe on the new error path.** `recv_msg.fd[0..1]` are set to
  `-1` before any `goto done`, and `done:` closes any descriptor the OOB carried,
  so the new branch neither leaks nor closes a stale descriptor.
- **The port cleanup drops both references.** On a failed `nxt_unit_get_port`, the
  function removes the request from `awaiting_req`, deletes the port from the hash
  (`remove=1` is a container removal, not a reference) and unlinks it from the
  process list, then releases one reference; the caller's
  `nxt_unit_request_info_release()` releases the other (`use_count` starts at 2).
  No leak, and no hash entry left to mislead a later request.
- **The router's second expiry reuses the acknowledged-request path**, which the
  large new comment walks through (unlink cancels the RPC; a late acknowledgement
  or response finds no handler and is dropped; the shared memory stays with the
  worker because the retraction lost).

## Tests

Both extended test files are pre-existing and registered on master
(`nxt_router_app_timeout_test.c` in `auto/sources:206`, called from
`src/test/nxt_tests.c:384`). The router test's header states the expected
behaviour — a claimed request is not answered at the first expiry, that expiry logs
**one** alert and re-arms, the second expiry answers 503, and an unclaimed request
is still answered at once — and it counts alerts, so a re-arm that fires twice or a
missing alert fails the test. The libunit test asserts the emitted message is
`_NXT_PORT_MSG_RPC_ERROR` and drives the mmap-read failure path.

CI on the head: `c-tests`, `c-tests-asan`, `c-tests-almalinux8`, `c-tests-macos`,
`c-tests-pcre1`, `core`, `clang-ast`, `check-whitespace`, `ast-grep`,
`hardening-strict-fedora` (gcc and clang), the sanitizer legs and the language
legs — all pass.

## Blocker (release process, not code)

**No changelog entry.** The head touches neither `CHANGES` nor `docs/changes.xml`
(verified: `git diff --name-only origin/master...head` matches neither file, and the
1.37.1 section carries no line about a claimed-unacknowledged request). This is a
product fix in a patch whose whole purpose is that section; the release note must
name it before the tag.

## Nits

1. **The new assert.** `nxt_assert(req_rpc_data->app != NULL)` states an invariant
   the old code did not: a linked claimed request always holds a live application.
   The release path is where `app` is cleared (`src/nxt_router.c:1475`, next to the
   port release), and a released request is unlinked, so the premise looks right —
   but it is an abort in a timeout handler, and one sentence in the commit or a
   logged warning instead of an assert would be safer. I read the call sites, not
   the whole release function: treat the proof as the author's.
2. **Latency is now two timeouts.** A client whose request a dead worker claimed
   waits `2 × app.timeout` before the 503, where a live worker's overdue request
   waits one. Intentional and documented; worth one clause in the release note so
   it does not read as a bug.

## Related finding (whole train)

Verified on master at `678ef06d`: the 1.37.1 section holds 29 entries (25 Bugfix,
4 Change) and **none of them names #670 (the body part sent with the response
headers) or #671 (the engine port published before the engine thread)**, both of
which are merged. #673 (test-only) and #674/#676 do carry entries.

## Delta after the review (merged as `1f5028db`)

The branch was squashed before the merge, so the final head `7ccbdf5f` is not the
reviewed revision `0b793e81`. The merged diff is 9 files, +912/−72 against the
7 files and +787/−72 reviewed here. The two extra files are `CHANGES` and
`docs/changes.xml`, which carry the entry the release blocker asked for, so the
blocker was closed in the merge.
