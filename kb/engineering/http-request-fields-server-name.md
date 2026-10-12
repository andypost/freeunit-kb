# HOST, server_name, local_addr — what the router hands an application

_Verified against master and the java-server-name-ipv6 branch, 2026-09-12._

## Who writes what

`nxt_http_application_handler()` (src/nxt_http_request.c) is the only producer of
`server_name`, and `nxt_router_process_http_request()` (src/nxt_router.c:7212) the only
writer into the app-visible `nxt_unit_request_t`:

- `r->host.length != 0` → `server_name = r->host`
- otherwise → the literal `"localhost"`

So `server_name` is never empty and never NULL. An *empty* `Host:` value also lands in
the literal branch: `nxt_http_validate_host()` leaves `length == 0` for it, while
`r->host.start` is set, and the producer tests length, not the pointer.

`r->host` comes from `nxt_http_request_host()` → `nxt_http_validate_host()`, which:
rejects a second Host field (400), rejects `/` (400), rejects an empty label (`..`),
strips the port with the `[literal]` case understood, strips one trailing dot, and
lowercases only when an ASCII uppercase was present (pool copy; otherwise the value
stays a slice of the raw field).

## Three different fields, three different meanings

| field | source | example |
|---|---|---|
| `server_name` | the name the CLIENT used (Host, normalised) | `example.com`, `[::1]` |
| `local_addr` + `local_port` | the listener the connection arrived on (`nxt_sockaddr_address`) | `10.0.0.1`, `8080` |
| `remote` | the peer address, **no port** | `2001:db8::1` |

`local_addr`/`local_port` are filled unconditionally for every app-bound request
(router.c:7198-7204). The "interface" is therefore already available — in its own
field, read by `getLocalAddr()`/`getLocalName()`/`getLocalPort()`. Putting it into
`server_name` would duplicate a field and substitute an address for a name, which an
app building an absolute URL or a redirect out of `getServerName()` would then emit.

## Why the literal is "localhost"

- Unit has no configured server name — no config directive supplies one; the only name
  in play is the one the client sent.
- The literal dates from `e929d082` (2019, vbart, "Fixed processing of SERVER_NAME
  after 77aad2c142a0"): Host normalisation moved SERVER_NAME to the router's normalised
  copy, and `nxt_unit_split_host()` was **removed because it did not work with IPv6
  literals** — the same class of bug as the one fixed in the Java module in 2026 (#327).
- All other modules read `server_name` (php `SERVER_NAME`, python, ruby, perl, wasm);
  the javac/JNI module was the last one still parsing the raw Host field itself.

## Trust model

`server_name` is client-controlled (any build-a-URL-from-Host framework is exposed to
Host-header poisoning: cache and password-reset link forgery). That is not changed by
normalisation and is the app's business — the router only guarantees shape, not
authenticity. Unit does not require Host on HTTP/1.1, so a request without it reaches
an app with `server_name = "localhost"`.

Field values may carry obs-text: the header scanner rejects only bytes `< 0x20`, so
0x80-0xFF pass and reach `NewStringUTF` (JNI expects valid modified UTF-8; invalid
input is undefined). Pre-existing in every JNI string conversion, not specific to this
field.

## Residual defects in the Java module (deferred from #327)

The same file splits `local_addr` and `remote` at the first `:`, although both carry an
address with no port:

- `getLocalPort()` → hard-coded `80` on IPv4
- `getRemotePort()` → `80` on IPv4, `0` on IPv6
- `getRemoteHost()` → empty string for an IPv6 peer
- there is no remote-port field in `nxt_unit_request_t` at all

Those helpers also temporarily store `'\0'` at `str[len]` before `strtol`/`NewStringUTF`.
That is harmless by construction: the router allocates `+1` per string in `req_size` and
writes the terminator itself, so the store rewrites the byte that is already `'\0'`
(`nxt_java_newString()` uses the same trick). The defect is wrong values, not memory
safety.
