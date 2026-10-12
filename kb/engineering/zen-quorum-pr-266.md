# zen-quorum: PR #266 — test(tls): stop asserting that a session resumes in the same instant
_gathered 2026-09-03 · keyless OpenCode Free tier_

**PR:** test(tls): stop asserting that a session resumes in the same instant
**Body:**
```
Draft — the TLS half is verified by local reproduction; the port-release half is not (see below).

Fixes the flakes tracked in #51, which has been open since 1.35.4 with "restarted now" as the only response. [Diagnosis and evidence in the issue comment.](https://github.com/freeunitorg/freeunit/issues/51#issuecomment-5485966568)

## Why the tests fail

Unit keeps no session cache of its own: `nxt_ssl_session_cache()` (`src/nxt_openssl.c:789-802`) sets the mode, size and timeout on one shared `SSL_CTX`. OpenSSL adds a session to the server cache **after** flushing its Finished message, so the insert lands fractionally after the client's handshake completes.

With one router engine the event loop serialises "finish handshake → add → accept next" and the window cannot be observed. With several, the client's immediate reconnect can be accepted by an engine that has not seen the insert yet, and a full handshake results.

That is OpenSSL's ordering, not a defect worth working around in Unit — a miss costs one extra handshake, and no real client reconnects a millisecond after its last handshake. But the tests assert that a session is resumable *in the instant it is established*, which Unit does not guarantee and which only ever passed because single-engine accept timing hid the window.

## It is not expiry, and not architecture

Alpine pipeline 468345 is a **retry** of a red run. The failures moved instead of clearing — `armv7` went green, `armhf` picked up `test_listeners_port_release`, and `aarch64` switched to `test_tls_session`, failing at the immediate resume where the session is configured with **no timeout** and the 300-second default applies. No expiry window is being raced.

The replaced comment claimed OpenSSL evaluates expiry in whole seconds. That has not been true since OpenSSL 3.2 (microsecond `OSSL_TIME`), and the flake it widened the window for was almost certainly this same race, mislabelled — which is why no timeout value ever fixed it.

## What changed

-
```

## Opinions
- **laguna-s-2.1-free** (2.1s): VERDICT=PARTIAL · CONCLUSION=NOT-CLEARED · RISK=low — only test timing logic changed, no production code touched · CONFIDENCE=high
- **ling-3.0-flash-fin-free** (29.6s): VERDICT=PARTIAL · CONCLUSION=PARTIALLY-CLEARED · RISK=medium · CONFIDENCE=medium
