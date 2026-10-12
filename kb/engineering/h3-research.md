# HTTP/3 — research result (W3, 2026-10-11)

Stream: TLS (module, h2, h3). Stage: research + one measured spike. No core code,
no date.

Branch `hermes/h3-research` in `freeunitorg/freeunit-exp`, pull request 24.
Artifacts: `exp/h3-spike/h3_spike.py`, `docs/exp/h3-verdict.md`,
`.github/workflows/exp-h3-spike.yml`.

## Measured

Userspace stack (aioquic 1.4.0, Python), one QUIC server + one HTTP/3 client on
loopback, one `GET /`:

| Where | QUIC handshake | H3 request round trip | Result |
|---|---|---|---|
| this host | 32.8 ms | 2.7 ms | 200, body `hello over h3` |
| clean CI runner | 35.4 ms | 0.8 ms | 200, body `hello over h3` |

What it proves: QUIC and HTTP/3 work in ordinary Linux userspace with one UDP
socket, one certificate, and no kernel feature. Each H3 stream is a normal request.
What it does not prove: any performance number for a C implementation. Python
numbers price the shape, not the cost.

## The three options

- **In-house QUIC in C** — own congestion control, loss recovery, connection IDs,
  packet timers. A second transport state machine beside the event engine. Highest
  effort and the largest bug surface; nginx carried its own QUIC and shipped HTTP/3
  experimental for years.
- **A library** — ngtcp2 + nghttp3 (C) fits the existing event model; quiche/Quinn
  arrive through FFI with a second runtime's timers. Either way the dependency is a
  permanent build, test and packaging commitment, and reverting it is a breaking
  packaging change.
- **Keep it at the edge** — nginx, HAProxy or a CDN terminates HTTP/3; the core
  stays HTTP/1 + HTTP/2. This is what the abandoned front-proxy plan relied on. It
  remains a legitimate operator deployment, not a missing feature.

## Prerequisites, in order

1. TLS 1.3 in the TLS module — QUIC requires it, and the ALPN token `h3` must be a
   first-class value there. **This is the only hard coupling between W1 and W3.**
2. HTTP/2 shipped — it validates the protocol-extension path, ALPN routing and the
   connection-object split.
3. Body streaming (D3) — a QUIC connection multiplexes many streams, so a buffered
   body parks behind flow control on every other stream. The KB named D3 a
   prerequisite for h2 and downgraded it to follow-on there; for HTTP/3 it stays a
   prerequisite.
4. A UDP event path — connection IDs, stateless resets and packet timers are new
   shapes for a TCP-oriented engine.

## Recommendation (hypothesis, maintainer's call)

- Do not start before HTTP/2 ships and D3 lands.
- Prefer a library over an in-house stack: the protocol is not the differentiator.
- Decide explicitly whether HTTP/3 is a core feature or an edge concern. That
  decision, not the estimate, sets the sequence.
- The KB estimate of 4–6 months after D3 assumes the library path and stays a
  hypothesis.

## Do not claim

- No number from this spike as a product number.
- No HTTP/3 mention in release notes, the site or a talk while this file is the only
  artifact.
- No date.

## Prior art checked

`nginx/unit` issue 554 (QUIC and HTTP/3) is open since 2021 with no implementation
— an unbuilt item, not a rejected one. `nginx` itself ships its own QUIC.

## Related

- `engineering/tls-module-prototype.md` — W1, verified module prototype
- `engineering/http2-in-freeunit.md` — the h2 stack, staging and the D3 tension
