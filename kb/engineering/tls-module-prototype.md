# TLS backend module — prototype results (2026-10-11)

Stream: TLS (module, h2, h3). Stage: W1 prototype, verified in CI.

## What was built

Prototype branch `hermes/tls-module-proto` in `freeunitorg/freeunit-exp`
(pull request 23). It is outside the server build; nothing is wired into `unitd`.

- `exp/tls-module/nxt_tls_backend.h` — the interface a loadable TLS module must
  expose, the single exported symbol `nxt_tls_backend()`, and the interface version
  the loader checks.
- `exp/tls-module/tls_backend_openssl.c` — an OpenSSL backend: context create and
  free, certificate and key, ALPN preference lists on both sides, the select
  callback, `conn_alpn_h2`.
- `exp/tls-module/smoke.c` — loads the module the way the core would, then drives
  three ALPN cases over a real handshake.
- `.github/workflows/exp-tls-module.yml` — path-filtered job that builds and runs it.
- `docs/exp/tls-module-interface.md` — the interface note.

## Verified result (clean runner, OpenSSL 3.5.5, cc 15.2.0)

```
PASS  interface                    backend="openssl" version=1
PASS  client offers no ALPN        negotiated ""
PASS  client offers http/1.1       negotiated "http/1.1"
PASS  client offers h2             negotiated "h2"
OK (0 failures)
```

## The trap the run found — reuse this

The ALPN select callback must set `*out` to the protocol **name**, not to the
length-prefixed entry. Writing `*out = p` (the entry) leaks the one-byte length
prefix into the protocol name in the ServerHello; the client then answers with a
`decode error` alert. Correct form:

```c
for (p = in, end = in + inlen; p < end && *p > 0; p += 1 + *p) {
    if ((size_t) *p == strlen(want) && memcmp(p + 1, want, *p) == 0) {
        *out = p + 1;      /* the NAME, not the length byte */
        *outlen = *p;
        return SSL_TLSEXT_ERR_OK;
    }
}
return SSL_TLSEXT_ERR_NOACK;   /* no overlap: no ALPN, HTTP/1 follows */
```

Two more facts worth keeping:

- **No overlap must answer NOACK, not an empty protocol.** An empty answer breaks
  a plain HTTP/1 client; NOACK sends no ALPN extension and HTTP/1 follows.
- **Diagnosis method:** run the no-ALPN case FIRST. If a plain handshake passes
  while the ALPN cases fail, the fault is in the extension, not in the connection
  setup. The prototype's first failure message ("handshake did not complete") hid
  four different steps for two CI cycles; naming each step and dumping
  `ERR_get_error()` cut it to one.

## Where this sits in the stream

- The HTTP/2 stack installs ALPN inside the TLS backend file (`src/nxt_openssl.c`,
  `nxt_openssl_alpn_select` / `SSL_CTX_set_alpn_select_cb` /
  `nxt_openssl_conn_alpn_h2`, +61 in pull request 463). No protocol file exists on
  `master`; the stack lives in pull requests.
- Consequence: the module must own ALPN, or the core keeps its TLS dependency after
  the module lands.

## Still open

- TLS 1.3: what the callback returns when there is no overlap, and whether the
  server still answers HTTP/1. The prototype pins TLS 1.2 on purpose.
- Certificate reload ownership: core or module.
- Health reporting to `/status` and the error log.
- Load model: runtime `dlopen` with a built-in fallback, or a fixed module path
  chosen at configure time.

## Related

- `engineering/http2-in-freeunit.md` — the h2 stack and its staging
- `strategy/unit-work-process.md` — the TLS stream, its tracks and rules
