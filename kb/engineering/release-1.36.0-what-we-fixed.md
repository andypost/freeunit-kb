# FreeUnit 1.36.0 — What We Fixed

## By Category (with security impact)

---

### 🔴 Security: Configuration Injection (5 fixes)

**C-string NUL injection** — reject empty and embedded-NUL values in config
strings used as `\0`-terminated C strings. Before: `"user\0root"` silently
became `"user"` (truncation). Now: rejected at config load.

| Surface | Fixed | Impact |
|---------|-------|--------|
| `user`, `group`, `working_directory`, `stdout`, `stderr`, `executable` | Empty + NUL | Target confusion → another user/command |
| Unix socket pathname addresses | Empty + NUL | Socket path truncation |
| `access_log` (string + object forms) | Empty + NUL | Log file redirection |
| TLS `certificate` + njs `js_module` names | Empty + NUL | Wrong cert/module loaded |
| PHP `options.file` php.ini path | Empty + NUL | Malicious php.ini loaded |
| Templated `share`/`chroot` paths (variable-resolved) | NUL | Static file served from wrong directory |

```
Before: "user": "www-data\0root" → parsed as "www-data" (truncated after NUL)
After:  Config load fails with clear error → safe
```

---

### 🔴 Security: Path Traversal (3 fixes)

**rootfs as `/`** — reject `"/"`, `"/."`, `"/foo/.."` → chroot("/") is a no-op,
defeating isolation silently.

**openat2 TOCTOU** — mount rootfs automount destinations via `/proc/self/fd`
on the openat2-validated descriptor, not by re-resolving the path.

```
Before:  openat2(RESOLVE_BENEATH, "/var/www") → OK
         mount("/var/www", ...) ← symlink could have been swapped between calls
After:   openat2(RESOLVE_BENEATH, "/var/www") → fd = 5
         mount("/proc/self/fd/5", ...) ← TOCTOU eliminated, same inode
```

**NUL in cgroup path + rootfs isolation** — reject embedded NUL in `rootfs`
and cgroup `path`.

---

### 🔴 Security: HTTP Smuggling Prevention (3 fixes)

**Duplicate upstream Content-Length** — both headers dropped, body read to EOF.

```
Before:  upstream sends: Content-Length: 20, Content-Length: 6, body(20 bytes)
         Unit relays Content-Length: 6, body(20 bytes) → downstream sees 6,
         reads 6 bytes, 14 bytes leak into next response on keep-alive → smuggled
After:   Both Content-Length headers dropped. Body read to EOF. Keepalive disabled.
```

**Proxy keepalive disable** — `r->inconsistent` flag no longer cleared on clean
upstream close. Separate `r->truncated` bit for genuine body truncation.

**Control characters in `set_headers`** — CR, LF, NUL, DEL rejected at config load.

```
Before:  "set_headers": {"X-Injected": "ok\r\nContent-Length: 0\r\n\r\nHTTP/1.1 200"}
         → HTTP Response Splitting: attacker injects headers/body
After:   Config load rejected: control char in header value → safe
```

---

### 🔴 Security: IPC & Port Hardening (3 fixes)

**SCM_CREDENTIALS** — privileged IPC message types authorized by kernel-validated
sender PID. Received descriptors closed on every rejected privileged message.

**Control socket peer UID** — requires matching peer UID (root or Unit's own UID).
`control-user`/`control-group`/`control-mode` are now defense-in-depth, not a
delegation mechanism.

**Port queue bounds** — queue item size capped at slot data bound.

---

### 🔴 Security: WebSocket RFC 6455 Hardening (5 fixes)

| Fix | Consequence before |
|-----|-------------------|
| Reject truncated extended-length frames | Frame with 2-byte payload claiming 8-byte extended length → OOB read |
| Validate 64-bit extended-length MSB | RFC 6455: MSB must be 0 → previously ignored |
| Fix no-op frame-size decrement | Could copy bytes beyond declared payload |
| Bound Java `sendWsFrame` JNI arguments | OOB in Java bridge |
| Guard `pending_payload_len` overflow in Python ASGI | Integer overflow → OOB |

---

### 🔴 Security: libunit & Language Bounds (4 fixes)

**Shared memory bounds** — request-header fields region bounded against message
size. Serialized pointers validated. Cached header-field indexes validated before
use. Shared-memory offsets range-checked: `chunk_id`, `chunk_id+nchunks`, `sptr`.

**App-supplied argument bounds** — across all language bindings:
- PHP: header skip, realpath, PATH_INFO bounds
- Python WSGI + ASGI: argument validation
- Perl: ERRSV scrub
- Java: `InputStream.readLine` off/len
- WASM: guest offsets

**Response-buffer overflow** — size overflow rejected.

**libunit OOB** — Java `InputStream.read()` off/len range-checked.

---

### 🟡 Correctness: Crashes & Leaks (3 fixes)

**Controller debug-build crash** — active-connection tracking change crashed on
control-socket close. Now routes through engine tracking macros.

**Controller fd leak** — accepted control connection fd leaked on init/body
allocation failure.

**Buffer-allocation failure** — port read handlers: orderly teardown instead of
NULL-pointer dereference. Write error after partial send: immediate error handler
routing. Engine teardown: timer batching array freed.

---

### 🟡 Correctness: Race Conditions (3 fixes)

**Go port-fd double-close** — `getUnixConn()` wrapped raw descriptor (which
`net.FileConn` dups). Deferred `Close()` closed original fd while libunit owned it.
```
Before:  fd = 7 (libunit port)
         dup(7) = 8 → net.FileConn wraps fd 8
         defer Close(8) → closes fd 7 (alias!) → libunit EBADF
After:   fd = 7 → dup2(7) = 8 → net.FileConn wraps fd 8
         libunit remains sole owner of fd 7 → safe
```

**rootfs automount reload race** — worker mount namespace propagation severed
before mounting. Per-worker automount reaped with namespace, not unmounted from
host. Config reload no longer races old generation teardown vs new mount.

**Port callback window** — libunit holds port reference across out-of-mutex
`add_port` callback. Concurrent destroy can't free the port mid-callback.

---

### 🟢 Observability: OpenTelemetry (6 fixes + features)

| Change | Before | After |
|--------|--------|-------|
| Malformed traceparent | HTTP 500 rejected | Trace restarted per W3C, header dropped |
| Traceparent validation | None | Segment lengths, lowercase hex, no all-zero IDs, no `ff` version |
| Duplicate traceparent | Context lost | First valid accepted, second dropped |
| Injected trace fields | Garbage flag bits → random header drop | Zero-initialized |
| Sampling decision | Ratio-based only | ParentBased: remote parent flags honoured |
| Service name | "NGINX Unit" | "FreeUnit" (configurable) |

**Infrastructure:**
- OTLP/gRPC reintroduced (tonic, h2c plaintext, compiled into every `--otel` build)
- OTLP/HTTP + OTLP/gRPC selectable at runtime
- Batch span processor on dedicated thread (blocking reqwest, no tokio runtime)
- Spec-compliant semconv: `http.method`, `http.status_code`, `http.route`, etc.

**Testing:**
- `fake_otlp` mock collector (`test/fake_otlp/`)
- `test_otel.py` test suite: span export, traceparent propagation, sampling, config validation

---

### 🟢 Infrastructure & Upgrades (4 changes)

**Graceful shutdown:**
- SIGQUIT: workers drain in-flight requests then exit
- SIGTERM: fast exit, drops workers immediately
- Two-phase listener close: disarm first, release fd after pending accepts drain

**Dependency upgrades:**
- wasmtime 35.0.0 → 36.0.12 (closes sandbox-escape CVEs)
- njs → 1.0.0
- OpenTelemetry Rust crates 0.24 → 0.32

**Active connection tracking:**
- In-flight connections on dedicated queue (symmetric with idle)
- `/status` API: exact connection accounting on all close paths

**CI & testing:**
- C unit-test suite now executed in CI (previously compiled but never run)
- Expanded test coverage: proxy framing, chunked relay, OTel 5xx, Java bounds

---

### Numbers

```
Fixes shipped:   38+
Security fixes:  20 (config injection, path traversal, HTTP smuggling,
                     WebSocket bounds, IPC auth, libunit bounds)
Features:         4 (SIGQUIT, 2-phase listener, OTel 0.32+gRPC, traceparent)
Upgrades:         4 (wasmtime 36, njs 1.0, OTel 0.32, CI tests)
Correctness:      6 (crashes, leaks, races)
Misc:             4 (CIDR, PCRE2, fd lifetime, routing)
```

### Security Advisories

| GHSA | Severity | Scope |
|------|----------|-------|
| GHSA-g6v8-r577-76jm | High | WebSocket OOB, cross-frame disclosure |
| GHSA-768w-qrh2-jjvh | High | Control socket peer-auth + NUL injection + cgroup TOCTOU |
