# Control API authentication (D7) — status, upstream precedent, design inputs

_Research 2026-09-10. Status of the fork's control-plane auth (roadmap D7 / audit-matrix A1)
and the historical discussion in upstream `nginx/unit` — the arguments a team discussion
must resolve before implementation._

**⚠️ TO DISCUSS WITH THE TEAM — this is the last open Phase-0 hole (A1, risk R1, weight 9.5).**


## 1. What the control API is, and why it is P0

The control API is FreeUnit's local REST interface (`/config`, `/certificates`,
`/applications/*`, `/status`). It fully rewrites the running config: add/remove apps,
swap listeners, execute code in the worker context. **Whoever reaches the socket gains
the authority of the `unitd` main process** — a privilege boundary, not just a feature.

Audit-matrix entry: **A1 — Control API authentication**, risk **R1 «control socket
takeover → full server compromise»**, weight **9.5**, CRITICAL. Product value: *«Enterprise-ready:
authenticated control plane»* — the only Phase-0 item marketable as its own Enterprise SLA tier.


## 2. What exists in the fork today (not "zero code")

`src/nxt_controller.c:727` `nxt_controller_check_peer_cred()` — commit **`5f795d19`**
(2026-06-11, shipped **1.36.0**; documented in `docs/man/man8/unitd.8.in`):

```
if (c->remote->sa_family != AF_UNIX)  return NXT_OK;     // ← skip on non-unix
SO_PEERCRED → cred.uid ; if (cred.uid != 0 && cred.uid != nxt_euid) → reject
```

Called from `nxt_controller_conn_init():810` — a local peer with a different UID is
rejected **before the request is read**. So on a UNIX socket (Linux/BSD) there IS a gate.
The `--control-mode/-user/-group` file perms are **defense-in-depth, not the boundary**
(man page is explicit).

### The two gaps that keep A1 open

1. **TCP control socket bypasses the gate entirely.** The man page allows `--control`
   in "IPv4, IPv6, or UNIX-domain format", and `nxt_sockaddr_parse()`
   (`src/nxt_runtime.c:998`) parses any form. But the gate is `if (sa_family != AF_UNIX)
   return NXT_OK` → **no check on TCP**. `--control 0.0.0.0:8080` = anyone on the network
   reads/writes the config. No bearer token, no mTLS, no IP allow-list.
2. **Same-UID peers pass.** The gate admits `cred.uid == nxt_euid`. Any process under the
   same user as `unitd` (including a non-isolated app) walks through legitimately.

**Missing (D7 on roadmap):** bearer-token on `/control/*`; mTLS; a gate for the TCP
control socket; same-UID intra-process distinction; enterprise docs beyond the unix note.


## 3. "Zero artifacts" — precise reading

- **Issue:** search `control api auth` across all states → **0 results**.
- **PR:** search `bearer`/`control-plane` → hits #144 (GHSA backport), #280 (start bound),
  #111 (engine refactor) — **all unrelated**.
- **Commit:** only relevant = `5f795d19` (the peer-cred gate). **No token/mTLS code.**

So read the digest line "artifacts: none" as **"no open issue/PR and no bearer/mTLS
implementation"** — NOT "nothing in the code". Partial mitigation exists; the full D7
solution has zero artifacts.


## 4. Upstream `nginx/unit` precedent — the arguments (team discussion input)

### #1315 «[Feature Request] Basic Authentication for Control Socket» — OPEN, 2024-06-13 (ivanov17)
The direct D7 analogue: Basic Auth on the control API **for a TCP socket** (containers;
localhost-only API connections are impractical).
- **lcrilly (maintainer):** *«Nice idea, but I think it is insufficient without also making
  the transport confidential (with TLS)»* — Basic Auth without TLS sends the credential in clear.
- **ivanov17 (author):** production use (Ansible over the control API); protects against
  *«an infected container in the same container network»*; wants **per-endpoint** choice —
  leave `/status` unauthenticated for monitoring, protect config endpoints.
- Open since 2024, **no PR, no closed-by-PR**.

### #840 → PR #1000 — the upstream philosophy (the counter-argument)
#840 «Override control socket permissions» (2023-02, CLOSED). **lcrilly:** *«specify user,
group and mode for the Unix socket gives the right flexibility **without needing to switch to
a localhost TCP port (which `all` users can access)»*. Result: **PR #1000** (MERGED 2024-02-19,
ac000) added `--control-mode/-user/-group`. Upstream deliberately chose **unix file perms over
TCP auth**. Caveat (crabique): abstract sockets (`unix:@aaa`) break on `chmod("")`.
→ This is why our peer-cred gate (1.36.0) is the natural continuation of upstream's line.

### #307 「Use socket credential passing (SCM_CREDENTIALS / SCM_CREDS)」 — MERGED 2019 (i4ki)
**The direct ancestor of our peer-cred gate.** PR #307 added `SCM_CREDENTIALS`/`SCM_CREDS`
cmsg over the control socket *"to avoid having to pass the `pid` explicitly in the msg
payload"*, plus *"some IPC validations on obvious places. We need to review all comms in the
future."* Tested Linux/FreeBSD/OSX. So the **credential-passing primitive has existed since
2019** — upstream built the mechanism but never a *policy* (authz) layer on top. FreeUnit's
`nxt_controller_check_peer_cred()` (SO_PEERCRED, `5f795d19`) is the policy layer on a
9-year-old primitive; it is **not a novel invention**, which strengthens the D7 case (we
complete upstream's own unfinished direction rather than bolt on foreign machinery).

### #225 «Support TLS client side certificates» — OPEN, 2019-02-25 (zueve)
The mTLS half of D7 (`ssl_client_certificate`, nginx-style). **Open ~7 years, unimplemented.**
Why audit-matrix D7 says "bearer-token first, mTLS later".

### Periphery
- #1319 (2024, OPEN) — `unitctl` over SSH to the control socket.
- #1318 (2024, CLOSED) — `unitctl` deploy to many instances.
- #1266 (2024, OPEN) — CLI labels a TCP control socket as "unix" (cosmetic).
- **tippexs (maintainer):** roadmap priority — *«will not find its way into Unit within the
  next two releases»* (1.30 closed, 1.31 = WASM).


## 5. Arguments to resolve in the team discussion

1. **Basic-auth without TLS was rejected upstream** (lcrilly) — need TLS/mTLS, not a bare password.
2. **Upstream chose unix perms over TCP auth** (PR #1000) — "no TCP port all users can reach".
3. **mTLS stalled since 2019** (#225) — low historical priority.
4. **Per-endpoint auth** (ivanov17) — `/status` open, config protected. Strong design input.
5. **Priority was repeatedly low** (tippexs) — explains why it stayed open, not a technical block.

### Consequence for our design (proposed direction, to confirm with the team)
- Keep the **unix peer-cred gate** (already shipped) as the local boundary.
- Add a **bearer-token gate on the TCP control socket** (the actual gap), plus optional mTLS.
- Make it **per-endpoint**: keep `/status` optionally open for monitoring; protect config/certs.
- Enforce the gate **before `nxt_controller_process_request()`**.
- Preserve `unitctl` compatibility; document for enterprise (the SLA-tier selling point).

## 6. Open questions for the team
- [ ] Token model: static bearer vs. mTLS vs. both? Where does the token live?
- [ ] Scope: gate only the TCP path (unix already gated), or all endpoints uniformly?
- [ ] `/status` and `/metrics`: authenticated by default, or opt-out for monitoring?
- [ ] Same-UID local processes: is peer-cred sufficient, or do we need a token even on unix?
- [ ] Roadmap slot: which release carries D7 (it is ~3 weeks of work)?


## 7. Architecture option — TLS as a module (X11) — KEY PROPOSAL (2026-09-10)

Andrey's proposal: **move all TLS/SSL into a separate loadable module** (`tls.unit.so`),
"OpenSSL today, rustls tomorrow". This **dissolves** the core objection to D7 (§2/§4: "TCP
auth needs TLS needs OpenSSL always"). Recorded here because it changes the D7 decision.

### Why it matters for D7
- Today TLS is **compile-time** (`NXT_TLS`, `--openssl`/`--gnutls`, default `NO`) and woven
  into the **hot path** across **14 core files**: `nxt_conn.h` (`u.tls`), `nxt_conn_write.c`,
  `nxt_h1proto.c`, `nxt_listen_socket.c/.h` (`ls->tls`), `nxt_controller.c`, `nxt_router.c/.h`,
  `nxt_main_process.c`, `nxt_conf_validation.c`, `nxt_runtime.h`, `nxt_main.h`, `nxt_process.h`.
- If TLS is a module, **secure TCP control becomes opt-in**: you install `tls.unit.so` only
  if you want TLS at all. The core build stays **dependency-free** (no OpenSSL forced on
  everyone). So "TCP-control requires OpenSSL" → "TCP-control requires the TLS module".

### Precedent — "rust slim" is already in the tree
| Component | TLS stack | Note |
|---|---|---|
| `src/otel` (Rust) | **none** — deliberately plaintext (comment: rustls would pull aws-lc-sys / a 2nd OpenSSL) |
| `src/wasm-wasi-component` (Rust) | **rustls dropped** via `default-features=false` (removes `default-send-request`) |
| **`tools/unitctl` (Rust)** | **`rustls 0.23` + `hyper-rustls`** — a working rustls client |

→ A **rustls-based** TLS module is not hypothetical: rustls already ships in `unitctl`.

### Module-ABI reality
- The only dlopen ABI today is `nxt_app_module` (`nxt_application.c:385`) — it is **language
  app-module only** (php/python/java/wasm). TLS is NOT an app module.
- So X11 = a **new module category** (vtable interface replacing the `#if (NXT_TLS)` sites),
  not a reuse of `nxt_app_module`. Cost: indirection on the hot path + a versioned vtable.
  Boundary is clean because `src/nxt_tls.h` already abstracts the backend.

### The three TLS consumers — one module or many?
| Consumer | TLS side | Slim-Rust entry |
|---|---|---|
| TCP control socket (D7) | **server** (mTLS) | rustls module |
| ACME (Let's Encrypt, X9) | **client** (HTTPS to the CA) | rustls + minimal HTTP ("in-daemon Rust shim" per `acme-tls-plan.md`) |
| Scheduler / crontab (X10) | none of its own — **triggers** `acme/renew` | uses the ACME stack |

`scheduled-tasks-plan.md` already states the intent: *«If TLS becomes a module (tls.unit.so),
a scheduler inside the daemon lets FreeUnit plan its own updates — cert renewal, module swaps,
config re-apply — without external cron»*, with the diagram
`tls.unit.so (OpenSSL today, rustls tomorrow) + scheduler`.

### Open question for the team
**One shared `tls.unit.so` for control + ACME + otel/wasm, or scope it to control/ACME and
keep otel/wasm deliberately slim/plaintext?**
- Share → one stack, but otel/wasm lose their size/plaintext posture.
- Scope → two postures (TLS present vs absent), more build permutations.

## 8. Docker containers — what actually blocks them (2026-09-10)

Root tension: **a unix socket = "manage from inside"; a container = "manage from outside".**

| Blocker | Detail (code + KB) |
|---|---|
| **Default image runs as root** | `CMD unitd` with no `USER` (`pkg/docker/Dockerfile.minimal:115`); uid 999 `unit` created but never `USER`ed → peer-cred gate short-circuits (`geteuid()==0`, `nxt_capability.c:52`) |
| **`--user` fails on FS ownership, not capget** | `--user 1000` → `mkdir(/var/lib/unit/certs) failed (13)` / `bind(control.unit.sock.tmp) failed (13)`. Needs tmpfs/chown; `capget` is **allowed** by moby's seccomp — not the blocker |
| **Reaching the socket from outside** | the real reason for TCP — upstream #1315: *«containerized application… impractical to accept API connections only from localhost»* |
| **Bind-mounting the socket across the boundary** | `SO_PEERCRED` returns the **host** uid of the client, not the container's `unitd` uid → the gate **rejects a legitimate admin** |
| **userns-remap / rootless** | uid translation (host↔container) makes `cred.uid == nxt_euid` non-obvious |
| **Abstract sockets `unix:@name`** | supported on Linux (`nxt_sockaddr.c:613`); **no file → no FS perms → no chmod**; scoped to the **netns**, so with a shared netns (`--network=host`, shared container netns) a neighbour container can reach it, and **peer-cred is the only guard** (moby#14767) |

**Conclusion:** containers hit the fork — **unix (can't reach from outside) OR TCP (needs TLS →
OpenSSL)**. **X11 (TLS module) breaks that deadlock**: control-plane security stops imposing
OpenSSL on the whole core.

## 9. Updated D7 recommendation (supersedes §5 tone)

- **Target design:** TLS as module (X11) → TCP control with mTLS **opt-in**; unix peer-cred
  stays the **default, free** path.
- **Do NOT** ship a bearer-token on TCP without TLS (goes in clear — upstream rejected it).
- **Canonize** "unix-only + front with NGINX/SSH" as the default (docs already say this);
  secured TCP is an **opt-in module**.
- **Bundle with X9 (ACME) + X10 (scheduler)** — one TLS module serves control-API TLS *and*
  the ACME **client** side, which is the other missing 30% (`acme-tls-plan.md`).

## 10. Docs repo (`freeunitorg/docs`) — what it already says

The docs **cover the unix-only posture but never mention auth-on-TCP** (checked 2026-09-10):

- **`source/howto/security.rst` → «Secure Socket and State»** (label `security-socket-state`):
  - «Your control socket and state directory provide **unlimited access** to Unit's
    configuration, which calls for stringent protection.»
  - UNIX socket: «ensure it is available to **root** only» (`srw------- root root`).
    «UNIX domain sockets aren't network accessible; for remote access, use NGINX or SSH.»
  - **IP-based control socket: «avoid public IPs; they expose the control API and all its
    capabilities … manipulated by whoever is physically able to connect.»** Recommends the
    loopback address; then «any processes local to the same system can access the local
    socket, which calls for additional measures» → use NGINX to proxy.
  - **No bearer-token / mTLS / per-endpoint auth anywhere.** The docs' answer to remote
    access is "put NGINX (or SSH) in front" — i.e. externalize the auth, exactly the
    upstream stance (PR #1000).
- **`source/controlapi.rst`** — describes the socket type/address; defers security to
  `security-socket-state`. The OpenAPI section's «only IP sockets are supported now» is a
  limitation of the *OpenAPI tool image*, **not** an auth statement.
- **`source/news/2026/unit-1.36.0-released.rst`** — documents the peer-UID gate
  («require a matching peer UID (root or Unit's own effective UID) on the unix control
  socket … so control-user/-group/-mode are defense-in-depth») **and** a published advisory
  **GHSA-768w-qrh2-jjvh — «control-socket peer-authentication bypass», CVSS 8.8**
  (fixed in 1.36.0, backported to 1.34.x LTS).
- `source/security.rst` is a redirect stub (`:orphan:` → `../#reporting-issues`).

**Reading:** the docs already tell operators "unix-only, root-only, else front it with
NGINX/SSH". A D7 implementation would need to **update this section** (auth on the control
socket) and reconcile with the 1.36.0 advisory (which was about bypassing the *existing*
unix gate). Also note: the CVSS-8.8 bypass advisory means the unix gate had a real bypass
that 1.36.0 fixed — a reminder that "gate at the socket layer" needs adversarial review.

## 11. Quorum result (2026-09-10)

`zen_quorum` on the D7 design question, verdict options A/B/C/D/COMBO:

| Model | Verdict | Conclusion | Risk |
|---|---|---|---|
| muse-spark-1.2 | **COMBO** | NOT-CLEARED | high |
| ling-3.0-flash | **COMBO** | PARTIALLY-CLEARED | medium |
| nemotron-3-ultra | **COMBO** | NOT-CLEARED | high |
| muse-spark-1.3 | (no verdict — runtime error) | — | — |
| mimo-v2.5 / deepseek-free | FAIL (429 / 400) | — | — |
| nemotron-3.5 | format echo (invalid) | — | — |

**Consensus 3/3 → COMBO**: a **layered** approach —
1. **mTLS (client certs) required** on the TCP control socket (Basic Auth alone was already
   rejected upstream — lcrilly: insufficient without TLS);
2. **keep + harden** the unix peer-cred gate (close the same-UID gap: token even on unix, or
   a stricter check);
3. **per-endpoint granularity** — leave `/status` open for monitoring, gate config/certs
   (explicitly requested in upstream #1315).

All three converged independently. Note the models saw only the description (no diff — this
is a design question, so a blind-consensus vote is appropriate here; CONTEXT section is
verifiable fact from code/docs). Conclusion split NOT-CLEARED/PARTIAL = "direction agreed,
implementation not yet shown" — expected for a design decision.

## Related
- `engineering/audit-priority-matrix.md` — A1/R1 (weight 9.5), Phase-0 list.
- `engineering/acme-tls-plan.md` — X9; needs a TLS **client**; recommends an in-daemon Rust shim.
- `engineering/scheduled-tasks-plan.md` — X10; pairs with modular TLS.
- `engineering/rust-toolchain-policy.md` — the Rust build-time toolchain (otel/wasm/unitctl;
  rustls precedent in `unitctl`).
- `v1/roadmap.md` — D7, X9, X10, and the new **X11 (modular TLS)** + feature-relationship map.
- Fork code: `src/nxt_controller.c` `nxt_controller_check_peer_cred()` (:727),
  `nxt_controller_conn_init()` (:810); `src/nxt_runtime.c:998` (sockaddr parse);
  `src/nxt_tls.h` (backend abstraction); `auto/ssltls`, `auto/options:23`.
- Upstream: nginx/unit #1315, #840, PR #1000, #225, #1319, #1318, #1266.

