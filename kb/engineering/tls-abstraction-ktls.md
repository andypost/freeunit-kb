---
title: "TLS abstraction & kTLS in FreeUnit — variant A (multi-backend vtable) assessment"
description: "Code-level study of TLS coupling in FreeUnit: current nxt_tls.h/nxt_openssl.c, the real core-coupling surface of nxt_tls_conf_t, concrete OpenSSL/LibreSSL/BoringSSL API drift found in the tree, effort estimate for a true multi-backend vtable, and a kTLS integration plan incl. the multiprocess/SCM_RIGHTS risks."
tags: [freeunit, tls, ktls, refactor, roadmap, static, openssl, libressl, boringssl]
status: draft
updated: "2026-10-11"
---

# TLS abstraction & kTLS in FreeUnit

Scope: `freeunitorg/freeunit` (C core), `master` @ 2026-10-11. Read at code level, not
from web search. Every claim below carries a `file:line` citation.

Verdict up front:
- **Variant A (multi-backend `nxt_tls.h`) is much smaller than it looks: ~2–3 weeks.**
  The vtable skeleton already exists; the coupling surface is ~15 call sites, and
  most of them already go through a function pointer. The genuinely backend-specific
  work is confined to `nxt_openssl.c`.
- **kTLS is orthogonal and does NOT belong in the variant-A branch.** It is a
  data-path change behind the same interface, gated by a kernel probe, and it
  collides with FreeUnit's multiprocess + sendfile model in ways variant A never
  touches. Two independent tracks.
- **No reason found to revisit variant B** (TLS out of process). The hot path is
  unchanged by A; B would put serialisation + IPС on every record. Not reopened.

---

## 1. Current state of `nxt_tls.h` and `nxt_openssl.c`

### 1.1 `src/nxt_tls.h` (114 lines) — already a partial vtable

The header is NOT raw OpenSSL. It already declares an opaque, backend-neutral
interface. Inventory:

| Item | Line | Purpose |
|------|------|---------|
| `NXT_TLS_BUFFER_SIZE 4096` | 26 | record-buffering size (documented rationale, 16–24) |
| `nxt_tls_conf_t` (forward) | 29 | per-listener TLS config, opaque to core |
| `nxt_tls_bundle_conf_t` | 30, 54–61 | one cert bundle; holds `void *ctx`, `chain_file`, `name`, `next` |
| `nxt_tls_init_t` | 31, 85–92 | one-shot init input: `cache_size`, `timeout`, `conf_cmds`, `tickets_conf`, `conf` |
| `nxt_tls_lib_t` **vtable** | 35–44 | `library_init`, `library_free`, `server_init`, `server_free` |
| `nxt_tls_ticket_t(s_t)` | 32–33, 82–93 | session-ticket key material (defined in `nxt_openssl.c`) |
| `nxt_tls_bundle_hash_item_t` | 47–51 | lvlhsh key for SNI bundle lookup |
| `struct nxt_tls_conf_s` | 64–82 | **the config object**: `bundle`, `bundle_hash`, `tickets`, **`conn_init` fn ptr**, **`lib` fn ptr**, `ciphers`, `ca_certificate`, `buffer_size`, `no_wait_shutdown` |
| OpenSSL-only exports | 95–112 | `nxt_openssl_lib`, `nxt_openssl_log_error`, `nxt_openssl_copy_error`, test-fail macros |

**Key observation:** the abstraction is half-built and asymmetric. `nxt_tls_lib_t`
has only the *lifecycle* hooks (init/free of the library and of a server config).
The **data path is not in the vtable at all** — it lives in two other places:

- `nxt_tls_conf_t.conn_init` — a function pointer the core calls to attach TLS
  state to a connection (`nxt_h1proto.c:419`).
- `nxt_conn_io_t` — a *core* vtable (`nxt_conn.h:45–93`) that the OpenSSL backend
  swaps in wholesale at `nxt_openssl.c:1242` (`c->io = &nxt_openssl_conn_io;`).

So today there are **three** indirection points, not one: the lib lifecycle vtable,
the per-config `conn_init` pointer, and the connection's `io` vtable. A real
multi-backend design must decide whether to unify these or (better) leave
`nxt_conn_io_t` as-is and just add the backend's `conn_init`+io swap behind the
existing `nxt_tls_lib_t`.

### 1.2 `src/nxt_openssl.c` (1933 lines) — the only live backend

Function inventory (declarations 104–152, definitions as noted):

| Function | Line | Role |
|----------|------|------|
| `nxt_openssl_library_init` | 185 | `OPENSSL_init_ssl(OPENSSL_INIT_LOAD_CONFIG)`, version probe, `SSL_get_ex_new_index` |
| `nxt_openssl_library_free` | 216 | library teardown |
| `nxt_openssl_server_init` | 222 | **builds the `SSL_CTX`**: options, key file, ciphers, verify, client CA, SNI callback registration, session cache, conf-cmd apply, ticket keys, sets **`conf->conn_init`** (371) |
| `nxt_openssl_chain_file` | 397 | PEM chain load via `BIO_new(BIO_s_fd())` + `PEM_read_bio_X509_AUX` |
| `nxt_ssl_conf_commands` | 510 | applies `ssl.conf_commands` via `SSL_CONF_cmd` (guarded) |
| `nxt_tls_ticket_keys` | 592 | session-ticket key setup |
| `nxt_tls_ticket_key_callback` | 703 | per-ticket encrypt/decrypt callback |
| `nxt_ssl_session_cache` | 828 | session cache mode/size/timeout |
| `nxt_openssl_cert_get_names` | 844 | SAN/CN extraction for SNI |
| `nxt_openssl_name_text` | 959 | X509 name accessor (replaces deprecated `X509_NAME_get_text_by_NID`) |
| `nxt_openssl_bundle_hash_test/insert` | 1001/1012 | SNI bundle table |
| `nxt_openssl_servername` | 1066 | **SNI callback**: `SSL_get_servername` → `SSL_set_SSL_CTX` |
| `nxt_openssl_find_ctx` | 1150 | bundle lookup by SNI |
| `nxt_openssl_server_free` | 1172 | frees `SSL_CTX` chain |
| `nxt_openssl_conn_init` | 1197 | **per-conn**: `SSL_new`, `SSL_set_fd`, `SSL_set_accept_state`, `SSL_set_ex_data`, **`c->io = &nxt_openssl_conn_io`**, **`c->sendfile = OFF`**, start handshake |
| `nxt_openssl_conn_free` | 1257 | `SSL_free` + buffer free |
| `nxt_openssl_conn_handshake` | 1274 | handshake FSM |
| `nxt_openssl_conn_io_recvbuf` | 1368 | `SSL_read` |
| `nxt_openssl_conn_io_sendbuf` | 1403 | coalesce → `nxt_openssl_conn_io_send` |
| `nxt_openssl_conn_io_send` | 1419 | **`SSL_write`** (the data path) |
| `nxt_openssl_conn_io_shutdown` | 1459 | `SSL_shutdown` |
| `nxt_openssl_conn_test_error` | 1580 | `SSL_get_error` classification |
| `nxt_openssl_conn_io_shutdown_timeout` | 1664 | shutdown timer |
| `nxt_openssl_conn_error` | 1681 | error logging |
| `nxt_openssl_log_error_level` | 1760 | errno→log-level mapping (PR #639) |
| `nxt_openssl_log_error` / `nxt_openssl_copy_error` | 1852/1871 | public error helpers |

The backend-private connection struct:

```c
typedef struct {              /* nxt_openssl.c:37-47 */
    SSL               *session;
    nxt_conn_t        *conn;
    int               ssl_error;
    uint8_t           times;      /* 2 bits */
    uint8_t           handshake;  /* 1 bit  */
    nxt_tls_conf_t    *conf;
    nxt_buf_mem_t     buffer;
} nxt_openssl_conn_t;
```

**This struct is the whole "backend-private state" the abstraction must hide.** The
core never sees it — it only holds `c->u.tls` as `void *` (`nxt_conn.h:149-153`).

---

## 2. How the core uses `nxt_tls_conf_t` — the real coupling surface

Two questions matter: (a) is `nxt_tls_conf_t` used only as config storage, or do
core files reach into TLS-specific functions? (b) which of these go through an
indirection already?

### 2.1 The `NXT_TLS` guard sites across the core

`NXT_TLS` appears in: `nxt_main.h`, `nxt_runtime.h`, `nxt_router.h`,
`nxt_router.c`, `nxt_h1proto.c`, `nxt_conn.h`, `nxt_conn_write.c`,
`nxt_listen_socket.h`, `nxt_listen_socket.c`, `nxt_process.h`, `nxt_main_process.c`,
`nxt_conf_validation.c`, `nxt_controller.c`, plus `src/test/nxt_main_store_test.c`.
That is the blast radius of the compile-time guard — **14 core files (+1 test)**, the
ones that would carry a runtime `lib` pointer instead of `#if`.

### 2.2 Every core→TLS interaction, classified

| Site | What it does | Goes through indirection? |
|------|--------------|---------------------------|
| `nxt_router.c:616-621` | `rt->tls = nxt_service_get(services,"SSL/TLS","OpenSSL")`; `rt->tls->library_init()` | ✅ `nxt_tls_lib_t` vtable |
| `nxt_router.c:2661-2663` | on reconfigure, if `skcf->tls->bundle != NULL` → `server_free()` | ⚠️ vtable call, but reads `bundle` field directly |
| `nxt_router.c:4476-4489` | allocate `nxt_tls_conf_t`, set `no_wait_shutdown`, `tls_init->conf` | ❌ direct struct alloc/write |
| `nxt_router.c:5911-5913` | `skcf->tls->server_free()` | ✅ vtable |
| `nxt_h1proto.c:258` | `if (skcf->tls != NULL)` → pick idle read state | ❌ reads pointer only (OK) |
| `nxt_h1proto.c:396` | `tls = joint->socket_conf->tls` | ❌ pointer read (OK) |
| `nxt_h1proto.c:419` | `tls->conn_init(task, tls, c)` | ✅ `conn_init` fn ptr |
| `nxt_h1proto.c:553` | `r->tls = (c->u.tls != NULL)` | ❌ bool from opaque ptr (OK) |
| `nxt_h1proto.c:673` | redirect to HTTPS if `c->u.tls == NULL && …->tls != NULL` | ❌ bool (OK) |
| `nxt_h1proto.c:2682` | shutdown path if `c->u.tls != NULL` | ✅ `c->io->shutdown` |
| `nxt_conn.h:149-153` | `union { void *tls; } u;` | ❌ opaque slot (OK) |
| `nxt_sendbuf.h:40` | `void *tls;` in sendbuf | ❌ opaque (OK) |
| `nxt_conn_write.c:58-60` | `sb.tls = c->u.tls` | ❌ opaque copy (OK) |
| `nxt_runtime.h:31-32` | `const nxt_tls_lib_t *tls;` | ✅ vtable |
| `nxt_listen_socket.h:26-27` | `uint8_t tls; /* 1 bit */` | ❌ flag (OK) |
| `nxt_process.h:29-30` | `nxt_array_t *certs;` | ❌ unrelated (cert store) |
| `nxt_service.c:42-45` | service table `{ "SSL/TLS", "OpenSSL", &nxt_openssl_lib }` | ✅ registry |

**Finding: there are NO direct calls into OpenSSL-typed functions from outside
`nxt_openssl.c`.** Grep for `SSL_*`/`X509_*`/`BIO_*` outside the backend returns
nothing. The core touches:
- an **opaque pointer** (`c->u.tls`, `socket_conf->tls`),
- **two function pointers already** (`lib->server_free`, `conf->conn_init`),
- **one struct field by name** (`->bundle`, at `nxt_router.c:2661` and in
  `nxt_openssl_server_init`).

The one leak is `nxt_router.c:2661` reading `skcf->tls->bundle` directly. That is
the *only* place the core dereferences a field of `nxt_tls_conf_t` for a
decision, and it can be replaced by a boolean on the conf or a vtable predicate.

**Conclusion for the effort question:** the "real work to move behind a clean
interface" is essentially **(1)** add the missing data-path hooks to `nxt_tls_lib_t`
(today: only lifecycle + `conn_init`), **(2)** replace the `#if (NXT_TLS)` guard
with a runtime `rt->tls != NULL` where a second backend must coexist, **(3)** fold
`conn_init` into the vtable, **(4)** remove the single `->bundle` reach-through.
Not a rewrite.

---

## 3. Real OpenSSL/LibreSSL/BoringSSL incompatibilities found in the tree

These are version guards the author **already had to add** — evidence, not theory.
All of them are *within-OpenSSL* version drift (1.1.x vs 3.x vs 4.0), which is the
exact class a second backend multiplies.

| # | Site | Incompatibility | Guard today |
|---|------|-----------------|-------------|
| 1 | `nxt_openssl.c:30-34` | X509 name accessors constified in stages: `X509_NAME_get_entry`/`..._ENTRY_get_data` const from 1.1.0, `X509_NAME_get_index_by_NID` only from 3.0, returns const only at 4.0 | `NXT_X509_CONST` at ≥3.0 |
| 2 | `nxt_openssl.c:110,317,507` | `SSL_CONF_cmd()` / `SSL_CONF_CTX_*` — OpenSSL-only; **absent from BoringSSL, and LibreSSL ships only a partial/no implementation** | `NXT_HAVE_OPENSSL_CONF_CMD` probe (`auto/ssltls:90-101`) |
| 3 | `nxt_openssl.c:62-77,666-669` | Session-ticket key callback: `SSL_CTX_set_tlsext_ticket_key_evp_cb()` (EVP_MAC_CTX) from 3.0 vs deprecated `SSL_CTX_set_tlsext_ticket_key_cb()` (HMAC_CTX) | two-branch `#if`, MAC type typedef'd |
| 4 | `nxt_openssl.c:50,104-118` | `NXT_HAVE_OPENSSL_TLSEXT` — TLSEXT presence (`OPENSSL_NO_TLSEXT`) | feature probe (`auto/ssltls:104-117`) |
| 5 | `nxt_openssl.c:275` | `SSL_OP_IGNORE_UNEXPECTED_EOF` (1.1.1+) | `#ifdef` |
| 6 | `nxt_openssl.c:278-289` | `SSL_MODE_RELEASE_BUFFERS` — absent on old builds, unsafe before 1.0.1h | `#ifdef` + runtime version check |
| 7 | `nxt_openssl.c:193` | `OPENSSL_init_ssl(OPENSSL_INIT_LOAD_CONFIG,…)` (1.1.0+) | floor = 1.1.1 (`auto/ssltls:48-67`) |
| 8 | `nxt_openssl.c:239` | `SSLv23_server_method()` (deprecated alias; BoringSSL keeps it, but the modern name is `TLS_server_method`) | none — works on all three today, flagged for the port |
| 9 | `nxt_openssl.c:262` | `SSL_OP_NO_RENEGOTIATION` — not uniformly present outside OpenSSL 1.1.1+ | none |
| 10 | `nxt_openssl.c:247,300,438,483,1134` | `X509_get_ext_d2i`, `BIO_new(BIO_s_fd())`, `PEM_read_bio_X509_AUX`, `SSL_set_SSL_CTX` | none — all present in OpenSSL/LibreSSL/BoringSSL, but `BIO_s_fd`/`SSL_set_SSL_CTX` semantics differ subtly (BoringSSL has no `BIO_s_fd` default-file BIO; it uses `BIO_new_fd`) |

Items **2, 3, 7** are the ones that break first against LibreSSL/BoringSSL — and
they are already isolated behind probes/guards, which is exactly why the port is
mechanical rather than exploratory. Item 10 is where a second backend's own
`chain_file`/SNI code diverges — LibreSSL lacks `BIO_s_fd` in some builds and
BoringSSL never had it.

*(Marked: items 1–9 are read from the tree. Item 10's LibreSSL/BoringSSL specifics
are API-doc knowledge, flagged for verification during the port, not asserted as
"read from code".)*

---

## 4. Effort estimate — variant A (multi-backend `nxt_tls.h`)

Split by the three indirection points and the guard removal. Estimates in
engineer-weeks, one engineer familiar with the tree.

| # | Subtask | Files | Effort | Value |
|---|---------|-------|--------|-------|
| A1 | Promote the data path into the vtable: add `conn_init`, `conn_free`, `handshake`, `io` (or hand the backend its `nxt_conn_io_t *`) to `nxt_tls_lib_t`; drop the standalone `conf->conn_init` | `nxt_tls.h`, `nxt_openssl.c`, `nxt_h1proto.c:419` | 0.5 w | **High** — the load-bearing change |
| A2 | Backend registry: `nxt_service.c` already keys `"SSL/TLS"`; add selection at configure (`--tls=openssl\|libressl\|boringssl`) and a `NXT_TLS_BACKEND` macro | `auto/ssltls`, `auto/options`, `nxt_service.c` | 0.5 w | **High** — build-time backend choice |
| A3 | Replace `#if (NXT_TLS)` with runtime `rt->tls != NULL` only where a second backend must coexist; keep the guard where one build has TLS and another does not | 14 guard files | 1.0 w | **Medium** — only needed if backends ship in one binary; if build-time-selected, guard stays |
| A4 | Remove the one `->bundle` reach-through (`nxt_router.c:2661`) | `nxt_router.c`, `nxt_tls.h` | 0.25 w | Low |
| A5 | Second backend skeleton: `nxt_libressl.c` (fork of the OpenSSL backend, `SSL_CONF` path stubbed) | new file | 1.0 w | **High** — proves the interface |
| A6 | BoringSSL backend: `BIO_s_fd`→`BIO_new_fd`, ticket-cb, `SSL_CONF` absent, cipher config | new file | 1.5 w | Medium |
| A7 | Tests: parametrise `test/test_tls*.py` over backends; CI legs | `test/`, `.github/workflows` | 1.0 w | **High** |

**Total: ~2–3 weeks for A1–A4 + A5** (OpenSSL + one more backend, build-time
select). Add ~1.5 w for BoringSSL (A6) and ~1 w for the test parametrisation if a
second backend must be CI-gated.

**Shape:** near-term (A1–A2) is the interface itself and is *independent of any
specific second backend*; mid-term (A4–A5) proves it with LibreSSL; far-term (A6)
adds BoringSSL. A1+A2 alone (~1 week) deliver the "real vtable" the task asks
about, without shipping a second backend.

### 4.1 Precedent in-tree: `nxt_wasm_operations_t`

The WASM backend is the template. `nxt_wasm.h:35,131-134` declares
`nxt_wasm_operations_t` with `.init/.destroy/.exec_request/.exec_hook`, and
`nxt_rt_wasmtime.c:584` binds `nxt_wasm_ops`. The pattern the TLS work should
copy: **one `_operations_t` struct, one `extern const` instance per backend, one
`nxt_service_get` selection.** `nxt_tls_lib_t` is already 80% of this; it just
needs the data-path slots.

### 4.2 Precedents elsewhere (event-driven C servers)

- **nginx**: `ngx_ssl_*` is OpenSSL-coupled but selects at build
  (`--with-openssl`), never multi-backend at runtime. LibreSSL works via ABI
  compat, not a second driver.
- **HAProxy**: OpenSSL **and** LibreSSL/BoringSSL supported via build-time
  `USE_OPENSSL`/`USE_LIBRESSL`; compatibility shims in `include/haproxy/ssl_*`
  (`HA_OPENSSL_VERSION_NUMBER`, `HA_USE_*`). Closest match to variant A.
- **curl**: a real `vtls` layer (`Curl_ssl_backend` struct, `vtls/`) with per-backend
  files — the full vtable form, but curl's I/O model is far simpler than Unit's.
- **Postfix**: OpenSSL-only, build-selected.

**Take-away:** HAProxy's "build-time select + shim header" is the pragmatic model;
curl's full vtable is the aspiration. FreeUnit's `nxt_tls_lib_t` sits between them
and needs only the data-path slots.

---

## 5. kTLS — where the data path is, and how it would attach

### 5.1 The data path today

The per-connection TLS data path is entirely inside `nxt_openssl.c`:

- **Read:** `nxt_openssl_conn_io_recvbuf` (1368) → `SSL_read` (1379).
- **Write:** `nxt_openssl_conn_io_send` (1419) → `SSL_write` (1430), reached from
  `nxt_openssl_conn_io_sendbuf` (1403) and from the core's generic send path
  `nxt_sendbuf.c:258` (`c->io->send(...)`).
- **Attach point:** `nxt_openssl_conn_init` (1197) swaps `c->io = &nxt_openssl_conn_io`
  (1242). **This is the single seam** where a kTLS build would instead install a
  kTLS `nxt_conn_io_t` (or leave the kernel path and skip the userspace record loop).

After handshake, kTLS moves the record layer into the kernel (`setsockopt(sock,
SOL_TLS, TLS_TX/TLS_RX, …)`); the userspace `SSL_read/SSL_write` then speak
plaintext to a kernel-transformed socket. In FreeUnit terms: the post-handshake
`recvbuf`/`sendbuf` hooks become plain `read`/`write`/`sendfile`, and
`nxt_openssl_conn_io_send`'s `SSL_write` is bypassed.

### 5.2 sendfile × TLS today

**Critical finding:** TLS **disables sendfile on purpose.**
`nxt_openssl.c:1243` sets `c->sendfile = NXT_CONN_SENDFILE_OFF;` at conn init, and
the OpenSSL `nxt_conn_io_t` (`nxt_openssl.c:169-177`) has **no `old_sendbuf`** slot.

The generic (non-TLS) send path proves the contrast at `nxt_conn_write.c:201-202`:
a bare file buffer is routed to `nxt_conn_io_sendfile()` → `nxt_sendfile()` (the
zero-copy kernel path, `nxt_conn_write.c:222`). Under TLS that dispatch never
happens: `c->io` is the OpenSSL vtable, whose `sendbuf` (`nxt_openssl.c:1403`)
coalesces into memory and calls `SSL_write` (`:1430`). Per `nxt_sendbuf.h:10-13`,
"file buffers must be read in memory in advance" on any backend without a sendfile
slot.

Implication: **static files over TLS today cost a userspace read + encrypt + copy
per record, in `NXT_TLS_BUFFER_SIZE` (4096) chunks.** kTLS is precisely the fix —
with kernel TLS, `sendfile()` (or `SSL_sendfile` on OpenSSL ≥3.2) can push file
pages through kernel crypto and skip the userspace record loop. This is exactly why
the task links kTLS to "static".

### 5.3 Minimum OpenSSL and the SCM_RIGHTS / multiprocess risk

| Item | Finding |
|------|---------|
| OpenSSL floor | **1.1.1** (`auto/ssltls:48-67`, and the comment at :36-44 keeps it there for RHEL 8). **But** `SSL_sendfile` (the clean zero-copy TLS-static path) needs **OpenSSL ≥ 3.2**. So kTLS via `SSL_sendfile` would set a *second, higher* floor for kTLS users only — or FreeUnit drives `sendfile()` directly after `TLS_TX` is set, no `SSL_sendfile` needed (Linux kTLS offloads the socket; a plain `sendfile` to it works). **Recommendation: drive plain `sendfile()` post-`TLS_TX`, keep the 1.1.1 floor.** |
| Kernel | kTLS needs `CONFIG_TLS`/`tls` module (Linux 4.13+; aarch64/uDP offload later). Must be probed at **build** (`auto/` similar to `auto/sendfile`) *and* at **runtime** (the module may be absent) — build probe alone is not enough. |
| Ciphers | kTLS supports **AES-GCM-128/256, AES-CCM-128, ChaCha20-Poly1305, SM4** (SM4 needs ≥5.1 + crypto). Ciphers outside this set silently fail `TLS_TX` → must fall back to userspace. Config surfacing: an **explicit opt-in** `"tls": {"ktls": true}` on the listener (NOT auto-enable), because it changes cipher availability and the support matrix. |
| **Multiprocess / SCM_RIGHTS** | **The real risk.** FreeUnit passes listening sockets main→router via `SCM_RIGHTS`. A kTLS-enabled socket carries the `TLS_TX/TLS_RX` socket options and the per-socket crypto state in the *kernel*, tied to the socket. Two concerns: (a) the TX/RX transformation is installed **after** handshake, per accepted connection, so it is on the accepted fd, not the listening fd — `SCM_RIGHTS` of the listening socket is unaffected; (b) if any accepted connection fd is passed between processes (FreeUnit's router↔app uses the port/queue plane, not raw accepted sockets, for HTTP apps — but proxy peers and some paths may hold fds), the kTLS state travels with the fd, which is fine on Linux but must be **verified** — a `TLS_TX` socket that crosses a process boundary keeps its offload. **Handshake must still run in userspace** (kTLS has no userspace handshake API on the listen side without kTLS handshake offload, which is not in mainline). So the multiprocess model is *compatible* but the handshake→offload handoff must be per-connection. |
| Handshake | kTLS offloads the **record layer only**; the handshake stays in userspace via OpenSSL (or an in-kernel handshake helper where available). FreeUnit's handshake already runs in the router process per connection — so the kTLS install step slots right after `nxt_openssl_conn_handshake` completes. |

### 5.4 kTLS integration plan (files)

| Step | File | Change |
|------|------|--------|
| K1 | `auto/ktls` (new) | probe `SOL_TLS`/`TLS_TX` at build (like `auto/sendfile`) |
| K2 | `nxt_openssl.c` (post-handshake) | after handshake, if listener opted in and cipher is kTLS-supported, `setsockopt(SOL_TLS, TLS_TX)` (and `TLS_RX` for recv) |
| K3 | `nxt_conn.c` / new `nxt_ktls.c` | a kTLS `nxt_conn_io_t` whose `recvbuf`/`sendbuf` are plain `read`/`write`/`sendfile` |
| K4 | `nxt_openssl.c:1243` | stop forcing `sendfile = OFF` when kTLS is active — re-enable `sendfile` for static |
| K5 | `nxt_conf_validation.c` | validate `tls.ktls` + reject unsupported ciphers with a clear message |
| K6 | `test/` | kTLS tests need a **real kernel with the `tls` module** (not a plain container) — separate CI environment; reuse `test_tls*.py` framing for characterization |

**Ordering:** K4 (re-enable sendfile) is the payoff and depends on K1–K3. K6 needs
an environment FreeUnit's current CI does not have.

---

## 6. Verdict: one branch or two tracks?

**Two independent tracks, in this order:**

1. **Variant A first** (A1–A2, ~1 week; +A5 for LibreSSL, ~2 weeks total). It is a
   pure interface refactor, ships no new runtime surface, and lets the core stop
   `#if`-ing on TLS. It also *enables* kTLS by giving the data path a clean seam
   (K3's kTLS `nxt_conn_io_t` plugs into the same `c->io` swap that A1 formalises).
2. **kTLS second, on top of A** (K1–K6). It is orthogonal — a data-path
   implementation behind the interface A produces — but it carries its own
   support matrix (kernel module, cipher set, a *new* runtime-env CI), which must
   not block A's release cadence.

**Combining them is wrong** because: A is build-time/interface, kTLS is
runtime/kernel+data-path; A has no CI-env dependency, kTLS needs a real kernel
module; A touches 12 guard sites, kTLS touches the `nxt_conn_io_t` swap + `auto/`
+ cipher validation. Different reviewers, different failure modes. One issue each,
A tagged for the next minor, kTLS tagged as a spike→feature with its own kernel-gated
test job.

---

## 7. Open question for discussion (not decided here) — variant B

No codepath found that *forces* revisiting variant B (TLS out of process). B would
add serialisation + an IPC round-trip to **every** `SSL_read`/`SSL_write`, i.e. on
the hot path, for a benefit (process isolation of the TLS backend) that the
in-process vtable already gets by other means (backend is compiled into `unitd`,
no dynamic plugin boundary). **Returning as an open question:** is there a
regulatory/FIPS motivation for B (swap crypto module per deployment)? If not
recommended, B stays closed. No technical reason found to reopen it.

---

## Kernel-doc check via Context7 (2026-10-11)

Context7's public API (`https://context7.com/api/v1/search?query=…`, then `…/api/v1/<id>?type=txt&topic=…&tokens=N`, keyless) was queried against the Linux kernel documentation corpus (`/websites/kernel_doc_html`). It **confirms two load-bearing claims of this page**:

- **`sendfile()` works on a kTLS socket.** The kernel doc states it plainly: "Send file data with `sendfile()`: uses `sendfile()` to send a file's data over TLS records of maximum length (2^14)". So the recommendation above holds — drive plain `sendfile()` after `TLS_TX` and keep the OpenSSL 1.1.1 floor; `SSL_sendfile` (and its ≥3.2 floor) is not needed.
- **The cipher parameters are handed to the kernel**, not negotiated there: the doc's example fills `crypto_info.info.cipher_type = TLS_CIPHER_AES_GCM_128` plus `iv`/`rec_seq`/`key` and sets them with `setsockopt(SOL_TLS, TLS_TX/TLS_RX)` **after the handshake completes** — which is exactly why the cipher gate and the "install the offload right after `nxt_openssl_conn_handshake`" step are the right shape.

One new constraint found, worth a line in the plan: **with device offload, `sendfile()` data must not be modified** while the transfer is in flight ("Enable zero-copy transmission of `sendfile()` data directly to the NIC when device offload is enabled. The application must ensure the data is not modified…"). FreeUnit's buffer lifetime rules for the sendbuf path have to be checked against that before device offload is offered.

One new open item: the kernel doc also documents **`sendmsg()` with `TLS_SET_RECORD_TYPE`** — sending a TLS control message (alert, handshake) over a kTLS socket by giving the record type in a `SOL_TLS` control message. FreeUnit's shutdown path calls `SSL_shutdown` (close_notify); whether that alert travels correctly once `TLS_TX` owns the record layer, or must be sent as such a cmsg, is exactly the kind of thing a spike must answer.

Not verified there: **`SSL_sendfile` and its OpenSSL ≥3.2 requirement** — Context7's OpenSSL corpus (design docs and man sources) returned zero hits for `SSL_sendfile`, `kTLS` and `TLS_TX` on every topic tried, so that claim still rests on the API documentation alone. It is not on the recommended path.

## Measurement environment — resolved: the TLS ULP is the gate (measured 2026-10-11)

An earlier entry here said kTLS "cannot be exercised on the coordinator" and left the cause
undecidable. Both are retracted: the failure was a missing documented step, and it was the probe's
bug, not the kernel's.

`setsockopt(SOL_TLS, TLS_TX, …)` alone never reaches the TLS code. The kernel documentation requires
the TLS ULP first, after the connection is established — `setsockopt(SOL_TCP, TCP_ULP, "tls")`,
"Setting the TLS ULP allows us to set/get TLS socket options" — and `net/tls/tls_main.c` shows why:
`tls_init(sk)` is the ULP's `.init`, it refuses with `-ENOTCONN` unless `TCP_ESTABLISHED`, and it is
what creates the `tls_context` and swaps `sk_prot`. Without it, the socket layer answers the **generic
ENOPROTOOPT (92)** — the same errno an unknown level gets, which is exactly why the negative looked
like a kernel property.

Measured (kernel `6.8.0-136-generic` locally; ubuntu-24.04 / 6.17 and ubuntu-22.04 / 6.8 in CI, both
legs green): after `TCP_ULP=tls` the option is **accepted**, the peer receives `1703030033`
(application_data record) with the plaintext absent, and **`sendfile()` drives the kTLS socket**.
Cost, measured on CI (runs `38170196534` and `38170607310`, both legs green), normalised per MiB of
plaintext:

| Arm | system CPU / MiB | throughput |
|---|---|---|
| plaintext socket | 0.29–0.37 ms | 2 875–4 345 MiB/s |
| kTLS + `sendfile()` | 0.65–0.71 ms | 1 232–1 458 MiB/s |
| **userspace OpenSSL, 4 KiB writes** | **2.07–3.21 ms** | **69.5 MiB/s** |

kTLS is ~2.4× slower than a *plaintext* socket — that is the price of AES-GCM in the kernel, not a
verdict. Against the path it would replace (userspace OpenSSL) it is **17.7–21.0× the throughput with
3.2–4.5× less system CPU and roughly 30× less user CPU per MiB**, on two kernels (6.17, 6.8) and two
OpenSSL versions (3.0.13, 3.0.2). Caveat that bounds it: the OpenSSL arm is Python-driven, so it sets
the floor of the userspace path — a C driver narrows the multiplier while leaving the structure kTLS
removes (one read + encrypt + copy per 4 KiB record). Device offload was not exercised. Full method,
runs and caveats: `docs/exp/ktls-verdict.md`.

Snippet, and the probe's two bugs, in `engineering/ops-environment-facts.md` and
`docs/exp/ktls-verdict.md`.

## Key path — a real TLS 1.3 session handed to the kernel (measured 2026-10-11)

The socket options are the easy half; the key material is the half that decides whether a kTLS data
path can exist. Measured end to end: a real TLS 1.3 handshake (Python `ssl` over the system
OpenSSL, keylog enabled) → traffic secret → **HKDF-Expand-Label** (RFC 8446 §7.1/§7.3) → `TLS_TX`
with version `0x0304`, the negotiated AEAD cipher and a record sequence → plaintext written through
the raw fd → **the OpenSSL server decrypted what the kernel produced**.

| Runner | kernel | OpenSSL | sequence accepted | burst |
|---|---|---|---|---|
| ubuntu-22.04 | 6.8.0-1064-azure | 3.0.2 | **0** | 262 144 B / 7 KiB writes, all back, 86.6 MiB/s |
| ubuntu-24.04 | 6.17.0-1022-azure | 3.0.13 | **0** | 262 144 B / 7 KiB writes, all back, 97.5 MiB/s |

Two facts the C side must be built on:

1. **The application-data record sequence of TLS 1.3 starts at 0** — the sequence is per key epoch,
   so handshake records do not offset it. Nothing has to count handshake records.
2. The kernel's records, built from keys derived *outside* OpenSSL, are accepted by OpenSSL
   unchanged: the interface between the stacks is the key material, not a callback.

Open item, not a claim: on both CI images `TCP_ULP=tls` answered **EEXIST** before the probe was
fixed (the local kernel answered success) — something in that stack had already attached the TLS
ULP. The probe now treats EEXIST as the state `TLS_TX` needs, which is what it is, but the cause is
not established and the ULP state is not printed on the success path. Relevant before the C side
assumes it always owns the ULP.

Build probe and runtime capability API (step 2, capability layer) are in the tree:
`auto/ktls` → `NXT_HAVE_KTLS`, `src/nxt_ktls.[ch]` → `nxt_ktls_supported()`. See
`docs/exp/ktls-step2.md` for what is deliberately left out (key extraction, the `tls.ktls` opt-in,
the `nxt_conn_io_t` swap, close_notify via `TLS_SET_RECORD_TYPE`, SCM_RIGHTS).

## Review state of step 2 (recorded 2026-10-13)

Two reviewers work this branch, and both found real defects, so their findings are worth
carrying forward by number:

| source | where | what it is |
|---|---|---|
| Codex (`chatgpt-codex-connector[bot]`) | PR comments on `freeunitorg/freeunit`, and on `freeunitorg/freeunit-exp` PR #30 | automated per-commit pass; on this branch it reviewed the capability layer and the key work |
| The other side (Claude Opus 5.5) | `freeunitorg/freeunit-exp` PR #30 comments and issue #29 | the substantive reviews: a ten-finding review of `692bd126`, then checks of each fix commit |

Findings and where they stand:

| finding | subject | state |
|---|---|---|
| 1 | TLS 1.2 PRF left the label out of `A(0)` (RFC 5246 section 5) | fixed, vectors now from OpenSSL's `TLS1-PRF` (commit `647e210b`) |
| 2 | TLS 1.2 vectors agreed with the code by construction | fixed (same commit) |
| 3 | TLS 1.2 returned only the client key/IV; Unit is the server | fixed — the function takes the side |
| 4 | Probe sentinel `-1` equals `NXT_ERROR`, so a failed probe was never cached | fixed |
| 5 | Derived buffers not erased on return, including error paths | fixed (`ee700676`) |
| 6 | Sequence 0 applies to a client TX key only; a server writes tickets first, TLS 1.2 starts at 1 | fixed in the comment |
| 7 | Key block layout assumed a 4-byte fixed IV (RFC 7905 uses 12) | fixed — rejected, and the test asserts the rejection |
| 8 | No function filling the `linux/tls.h` structures, no field-level test | **open** |
| 9 | Includes before `nxt_main.h`, outside the guard | fixed |
| 10 | Probe reports "not available" without saying which step failed | open |
| nits | EEXIST comment, AF_INET-only loopback, `t[]` size | EEXIST comment and `t[]` fixed; IPv6 fallback still open |

Not a review finding but measured here: the probe's own `install_tx()` never passed the salt, which
is what the four `RECORD_LAYER_FAILURE` results were — the kernel's TLS 1.2 convention is
`salt` = the derived fixed IV, `iv[8]` = any initial explicit nonce, `rec_seq` = 1 in network order.

## Related
- `engineering/syscall-audit-kernel-requirements.md` (kernel-feature probe methodology)
- `engineering/control-api-auth-d7.md` (control-plane TLS)
- PRs: #370 (removed dead GnuTLS/CyaSSL/PolarSSL backends), #575/#639 (OTel/OpenSSL unlink, handshake-error logging)
