# Transfer-Encoding framing on the proxy path (PR #485)

Reviewed at head `7faf46b4782e` (fix/proxy-peer-transfer-encoding), 2026-09-26. Facts below are
from the diff and from the file at that head, not from a run.

## What the PR changes

`nxt_h1p_peer_transfer_encoding()` (src/nxt_h1proto.c, upstream response headers) used to accept
only the exact 7-byte value `chunked`; any other value left `h1p->chunked` at 0, so the response
was framed by Content-Length or by connection close and the chunk framing reached the client as
body bytes. It now parses the value as a comma-separated list of codings: SP/HTAB trimmed, empty
elements ignored (RFC 9110 5.6.1), names compared case-insensitively, `chunked` accepted only
once and only as the whole list. State carries across several `Transfer-Encoding` lines through
`h1p->transfer_encoding` (an existing 2-bit field on `nxt_h1proto_t`). `h1p->chunked` is now
derived once in `nxt_h1p_peer_header_read_done()` instead of being set inside the field handler.

Result states: `NXT_HTTP_TE_CHUNKED` only for a whole list of one `chunked` in any letter case;
everything else - unknown coding, `gzip, chunked`, `chunked, gzip`, chunked twice, empty value,
coding with parameters - is `NXT_HTTP_TE_UNSUPPORTED`, which the caller turns into 502. The proxy
never forwards `Transfer-Encoding` downstream (`field->skip = 1`).

## Asymmetry with the request path

`nxt_h1p_transfer_encoding()` (same file, :901) is UNCHANGED and still does the exact,
case-sensitive comparison. A client sending legal `Transfer-Encoding: Chunked` or `gzip, chunked`
gets 501 Not Implemented (`NXT_HTTP_TE_UNSUPPORTED` -> 501 at :975); a second `chunked` field gets
400. It fails closed, so there is no smuggling hole, but the same file now implements RFC 9112
6.1 in two different ways and the two handlers should be routed through one list parser.

## Order of checks vs bodyless responses

The new `NXT_HTTP_TE_UNSUPPORTED` arm (:2903) and the older chunked+Content-Length arm (:2917)
both sit ABOVE the bodyless-response block (:2953, `nxt_http_request_is_bodyless_final()`), whose
own comment states RFC 9112 6.3: a response to HEAD, and any 204 or 304, ends at the first empty
line "no matter what Content-Length or Transfer-Encoding say". So a 204/304/HEAD carrying a TE
the proxy cannot decode (e.g. `gzip, chunked`, `identity`) now yields 502 where it previously
yielded a normal bodyless response. Exact `chunked` in any letter case is unaffected: it reaches
the bodyless path and completes there.

## Premise checked

The new comment claims the upstream connection is closed after every response, so a framing error
cannot reach a reused connection. Corroborated in the tree: `nxt_h1p_peer_header_send()` always
asks the upstream for `Connection: close` (:2929-2930), so no upstream connection is reused.

## Test

`test/test_proxy_te.py` (new, port 7976 registered in test/fake_upstream/README.md) parametrises
chunked in lower/upper/mixed case and OWS, and 502 for TE+Content-Length, `gzip, chunked`,
`chunked, gzip`, two lines, chunked twice, `chunked;a=b`, `,`, and `identity`. The 502 cases also
assert the upstream body was not relayed, so the check is not vacuous. Gaps: every upstream
response carries `Connection: close`, so the no-reuse premise is exercised by code reading only,
and no case has a bodyless response with an undecodable TE.
