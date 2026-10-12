# zen-review PR #295 — proxy: complete a bodyless upstream response on its headers

_2026-09-08. Review of freeunitorg/freeunit#295 (OPEN, `fix/proxy-bodyless-upstream`).
_+349/−19, 5 files. Follow-up to #283 — its upstream half (base = 4aaede27, #283)._

## The bug (pipelined request lost; HEAD is the ordinary case)
`nxt_h1p_peer_header_read_done()` (`src/nxt_h1proto.c:2854`) armed the upstream
body framing from the upstream headers alone: `Content-Length` became
`h1p->remainder`, `Transfer-Encoding` armed `h1p->chunked_parse`. Neither the
request method nor the response status was consulted.

RFC 9112 §6.3 rule 1: a response to HEAD, and any 204/304, ends at the first
empty line after the header fields whatever `Content-Length`/`Transfer-Encoding`
say. The upstream sends the header block and — because
`nxt_h1p_peer_header_send()` (`:2541`) always writes `Connection: close` to every
upstream — then closes. `nxt_h1p_peer_closed()` (`:3172`) reads that as a cut body
(`h1p->remainder` still the advertised length, or `chunked_parse.last` clear), so
it sets `r->truncated` + `r->inconsistent`; `nxt_h1p_request_close()` (`:1929`)
then drops the client keep-alive (`h1p->keepalive &= !r->inconsistent`) over a
response that was never short. Any pipelined request is lost. Note: the first
response carries no `Connection: close` on the wire, because keepalive is cleared
in `request_close()` AFTER the header is sent — the client gets no signal.

## The fix
Decide framing where it is armed. In `nxt_h1p_peer_header_read_done()`: if
`nxt_http_request_is_bodyless_final(r, peer->status)` → `chunked = 0`, `remainder = 0`,
`peer->body = nxt_http_buf_last(r)`, `peer->closed = 1`, then `r->state->ready_handler()`.
Completion is identical to a body reaching its declared length (in `peer_body_process`).

## Refactor in `nxt_http_request.c` (the part to scrutinise)
- `is_bodyless` now takes `status` as a parameter (was reading `r->status`),
  because the proxy has to answer before `r->status` exists (it lives in
  `peer->status`; `nxt_http_proxy_header_read()` copies it into `r->status` one step
  later).
- Split **`is_bodyless_final`** (204/304/HEAD, NO 1xx) from `is_bodyless` (includes
  1xx). Correct: a 1xx is an interim response, "carries no body" ≠ "ends the
  exchange", and a caller needing the second must not get the first's answer.
- `websocket_handshake && status == 101` moved into `is_bodyless` (not `_final`).

## Verdict: APPROVE
- ✅ Completion path closed: `peer->closed = 1` → `nxt_http_proxy_send_body` sees
  closed → `peer_close()` + `nxt_mp_release(r->mem_pool)`. Same as a full body —
  no pool leak, upstream closed.
- ✅ `is_bodyless_final` precise; 1xx excluded on purpose, with honest comment
  (pre-existing 1xx out of scope).
- ✅ `b` deliberately not freed/forwarded: `peer->fields` point inside it
  (`nxt_http_parse_fields`); `header_read` copies field structs into `r->resp`
  where `$response_header_*` / `match` read them until request close. Returning
  the buffer to the engine cache would leave those pointing at reusable memory.
- ✅ Clean base — direct child of #283, no conflict replay.

## Test (strong)
`test_proxy_head.py` (250 lines): every case pipelines TWO requests in one write
(bodyless + GET /ok); the second response arriving is the regression assertion.
Covers HEAD+CL, HEAD+chunked, GET 204 (CL dropped), GET 304 (CL kept),
`$response_header_*` readability after completion. `check_pipeline` pins exact wire
shape (no `transfer-encoding`, no `close`, second response 200 with body OK).
Port 7978 reserved in the fake_upstream registry.

## Notes
- Refs #283 (downstream half of the same rule, already merged). Sibling reviews:
  pr-282 (compression shm), pr-288 (proto-death RPC), pr-283 (downstream no-body).
