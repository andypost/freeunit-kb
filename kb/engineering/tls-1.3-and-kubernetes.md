# TLS 1.3 and the cluster case — deep research (2026-10-11)

Question: what does TLS work have to deliver for 1.38, given that local networks and
Kubernetes need TLS and preferably 1.3? Priority: 1.38.

Method: read the tree at `origin/master`, the TLS validation surface, the OpenSSL
backend, the published docs, and the upstream issue archive. The stream plan
(`strategy/unit-work-process.md`) owns the sequencing; this file owns the facts.

## What already exists (evidence)

| Capability | State | Evidence |
|---|---|---|
| TLS 1.3 | **Available today**, but only through `conf_commands` | docs `configuration/index.rst` shows `"conf_commands": {"ciphersuites": "TLS_AES_128_GCM_SHA256:...", "minprotocol": "TLSv1.3"}` |
| Version pinning as a config member | **Absent** | no `set_min_proto_version` / `set_max_proto_version` in the backend; the TLS object has only `certificate`, `conf_commands`, `session` |
| Cipher control | Only via `conf_commands` (OpenSSL 3 conf commands), gated on `NXT_HAVE_OPENSSL_CONF_CMD` | same member list; the alternative path validates as `unsupported` |
| SNI, several certificates | **Works** | `SSL_CTX_set_tlsext_servername_callback` (`src/nxt_openssl.c:374`), `SSL_get_servername` (`:1083`); docs: an array of bundle names, the matching bundle answers a server name |
| Session resumption | Cache by size and timeout, plus tickets with a key | `nxt_ssl_session_cache` (`:828`), `session { cache_size, timeout, tickets }`; `SSL_OP_NO_TICKET` when no key is given |
| Client certificates (mTLS) | **Code path exists, surface does not** | `if (conf->ca_certificate != NULL)` → `SSL_CTX_set_verify(SSL_VERIFY_PEER)` + `SSL_CTX_load_verify_locations` + client CA list (`:335-367`); both `/* TODO: verify callback */` and `/* TODO: verify depth */` (depth pinned to 1) |
| Certificate rotation | Replaces a bundle in place | `PUT /certificates/<name>` replacement (1.37.0 CHANGES); bundle choice happens per handshake through SNI |
| OCSP stapling | Absent | only error-code handling around OCSP callbacks (`:1815`, `:2013`) |
| 0-RTT / early data | Absent | no `early_data` handling anywhere in `src/` |
| SNI-based per-name TLS policy | Absent | the servername callback picks a bundle, not a protocol set or cipher set |

## What the cluster and the local network actually need

At the edge, a proxy or ingress terminates TLS and the core needs nothing. Inside a
cluster, pods talk to pods: the request arrives at the application server with TLS
already on it because there is no proxy in the path (sidecars and service meshes are
an option, not a given). That yields four requirements, in order of how often they
decide an adoption:

1. **An explicit protocol policy.** Cluster policy scanners and security baselines
   want a field that says "TLS 1.2 minimum" or "TLS 1.3 only" and that fails at
   configuration time, not at the first handshake. `conf_commands` is a general
   escape hatch: keys are free-form, a typo is a runtime failure, and the field is not
   in the schema a scanner reads.
2. **Client certificates for service-to-service auth.** Short-lived certificates from
   a cluster CA (SPIFFE identifiers, step-ca, cert-manager) are the mesh-less way to
   authenticate a caller. The backend can verify them; nothing in the configuration
   surface asks for it, and the verify depth is pinned to 1 with a TODO.
3. **Rotation without a restart.** cert-manager rewrites a mounted secret. What the
   operator needs is a documented, atomic replacement path, and a clear statement of
   who triggers it (a control API call, not a file watcher).
4. **TLS 1.3 semantics that hold.** 1.3 removed renegotiation and the session cache
   works differently; tickets carry the resumption. Whatever the configuration says
   must hold on 1.3 too, and 0-RTT must be refused on purpose rather than inherited
   from a library default.

Small image, read-only rootfs and health probes are already satisfied or covered by
other work, and are not part of this list.

## Recommended 1.38 scope

**P0 — a TLS object that says what it means.** Add first-class members beside
`certificate`: a minimum and maximum protocol version, a TLS 1.3 cipher suite list,
and the pre-1.3 cipher list. Keep `conf_commands` for everything else. Rationale:
this is what a cluster manifest and a policy scanner consume; it is also the smallest
change that closes the "preferably 1.3" ask in a reviewable way.

**P0 — the client CA member, wired to the existing path.** Expose the CA certificate
and the verification policy (off / request / require) plus a configurable depth, and
give the two TODOs a real callback. Rationale: mTLS is the mesh-less answer, and the
backend already does the hard part.

**P1 — the TLS module carries 1.3 and the `h3` ALPN token.** The module interface
(W1, pull request 23) must treat 1.3 as a first-class version and `h3` as a
first-class protocol value. Rationale: QUIC requires 1.3, so the HTTP/3 track cannot
start without it. This is the only hard coupling between the two tracks.

**P1 — rotation, documented end to end.** State the contract: which control API call
replaces a bundle, what happens to connections in flight, and how a mounted secret
becomes a new bundle. Add a test that replaces a bundle while requests are running.

**P2 — refuse 0-RTT explicitly.** When 1.3 is on, early data must be off by default
with a documented reason (replay), rather than depending on the library default.

**Deferred, with the reason on record:** OCSP stapling (operators terminate at a
proxy that staples), ECH, post-quantum groups, per-SNI protocol policy. Each has a
dependency or a cost that does not fit the 1.38 window.

## What must be verified before any claim

- Whether a client CA is reachable today through a documented surface (`certificate`
  as an array is documented for SNI bundles; the client-CA path needs a check of its
  own before anyone writes "mTLS is supported").
- The lowest OpenSSL the build accepts, because `conf_commands` and therefore the
  only current route to 1.3-only depends on OpenSSL 3 conf command support, and the
  validator marks the member `unsupported` when the library lacks it.
- That the rotating-bundle path is atomic under load, not only that the API returns
  success.

## Do not claim

- Do not present `conf_commands` as a supported TLS 1.3 configuration. It is a route
  that works; it is not a feature.
- Do not claim mTLS, OCSP stapling, 0-RTT or per-SNI policy support.
- Do not put a version number or a date on any of the P0 to P2 items in public text
  before the code lands.

## Prior art

The upstream issue archive carries no demand thread for TLS 1.3 and no SNI request —
the mentions of Kubernetes are incidental, inside unrelated reports. The consequence
is worth stating plainly: the cluster case is not an upstream backlog item that can
be inherited; if it is wanted, it is written here.

## Related

- `engineering/tls-module-prototype.md` — W1 prototype, the module interface, ALPN trap
- `engineering/h3-research.md` — W3 research, the 1.3 coupling from the QUIC side
- `engineering/release-1.37.1-forecast.md` — 1.38 staging, to place this work
- `strategy/unit-work-process.md` — the TLS stream, tracks and rules
