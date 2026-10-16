# FreeUnit as a TLS-terminating reverse / MITM proxy for НУЦ-signed sites

**Date:** 2026-10-15 · **Ask:** run FreeUnit as a proxy so LAN browsers reach
RU sites signed by the regional НУЦ; the site sees FreeUnit's IP; FreeUnit
terminates client TLS; LAN users do not install the НУЦ root on each machine.
Are there ready Rust/Go solutions?

## Verdict

Not as asked. Two FreeUnit blockers and one fundamental limit.

### 1. Forward vs reverse proxy

The ask is a **forward / MITM proxy** (browser -> proxy -> arbitrary sites):
it needs HTTP `CONNECT` and on-the-fly certificate generation. FreeUnit is a
server-side **reverse** proxy with fixed listeners and virtual hosts. It has no
forward-proxy mode.

### 2. No upstream TLS (confirmed in code)

The `proxy` action takes only `{ "proxy": "<upstream-name>" }` plus common
action members — no `tls`/`verify` key. The proxy module and the upstream
module carry no `SSL_`/`X509_`/`verify`/certificate code. Upstream connections
are **plain HTTP**; FreeUnit terminates TLS only on the listener (client side).
=> FreeUnit cannot fetch an HTTPS origin as a TLS client. Blocker.

### 3. The certificate "downstream" problem (fundamental)

To serve browsers without installing the НУЦ root, the proxy must present a
certificate the browser already trusts:

- a public CA (ACME) — only for domains **the operator owns**;
- the operator's **own** CA root, deployed to the machines (GPO/MDM) — this
  swaps "install the НУЦ root" for "install your root": the same per-machine
  install, but one and centralised.

Otherwise the browser shows a warning. For arbitrary third-party sites, "no
root on any machine" is impossible with any software.

## Ready solutions

- **Reverse proxy with upstream TLS** (operator owns / fixed set): **Caddy**
  (on-demand TLS + internal CA downward, `reverse_proxy https://` + trusted CA
  upward), **nginx / Angie / HAProxy / Traefik** (`proxy_ssl_verify` +
  `proxy_ssl_trusted_certificate`). FreeUnit cannot until a TLS client lands.
- **Transparent MITM** (arbitrary sites): **Go** `elazarl/goproxy`,
  `go-gost/gost`, Envoy; **Rust** `hudsucker`, Pingora; classic **mitmproxy**,
  **Squid** `ssl_bump`. Still needs the operator's root pushed once.

## For FreeUnit

"Upstream TLS" (TLS as client) is a new feature — absent today. A symmetric TLS
layer is the natural output of the 1.38 TLS-module work (listener + upstream).
Candidate feature request.

## Ecosystem (adoption, checked 2026-10-15)

Stars: Caddy 78.0k, Traefik 65.2k, mitmproxy 45.6k, nginx 31.9k, Envoy 29.1k,
Pingora 27.6k, gost 7.6k, HAProxy 6.9k, goproxy 6.8k, hudsucker 380.

Pingora (`cloudflare/pingora`): **active but vendor-driven, not abandoned.**
Releases 0.6 (2025-08) -> 0.9.0 (2026-09); last commit 2026-09-11; ~100+
commits/yr; 27.6k stars, 1.77k forks. But the community side is thin: 314 open
issues, ~half never answered, ~5% closed in a year; outside PRs rarely merged;
maintained by a Cloudflare team. It is a Rust **library/framework** (build your
own proxy), not a turnkey product.

Stars measure popularity, not fitness.

## Angie and existing RU / НУЦ solutions (checked 2026-10-15)

**Angie** (`webserver-llc/angie`, mirror git.angie.software): **2.6k stars**, 44
open issues, last push 2026-10-13, BSD-2-Clause, "drop-in replacement for
nginx", forked by ex-nginx developers (RU). Built-in ACME with EAB, upstream TLS
(`proxy_ssl_*`), HTTP/3 on both sides; SM2/SM3/SM4 + NTLS (TongSuo) in-tree.

Patterns that already exist:

- **Reverse proxy trusting a НУЦ upstream:** nginx / Angie —
  `proxy_pass https://backend; proxy_ssl_verify on; proxy_ssl_server_name on;
  proxy_ssl_trusted_certificate <russian_trusted_root_ca.pem>;`. The proxy holds
  the НУЦ root once.
- **GOST-signed upstream (Минцифры/ЦБ):** **cpnginx** (nginx built with
  CryptoPro) — GOST + RSA termination, proxy to an internal nginx.
- **ACME issuance for НУЦ:** acme.sh (НУЦ fork) and wrappers
  `stufently/traefik-nuc-acme`, `BogdanNL/nuc-acme-sh-axelname-docker`.
- **Root certs:** `koenrh/russian-trusted-root-ca`, `cocaman/russian_root_ca`.
- **Analyser:** `CertIZDAT/russian-trusted-root-ca-analyzer` — 715 government
  sites require the Russian Trusted CA, 249 use self-signed; browsers mark them
  insecure except Yandex / custom Chromium, and only for whitelisted domains.
- **"No root on each device" is solved at the client:** `ezhkov-ph/bely-lis-android`
  (a Firefox build with the Russian Trusted Root CA embedded), Yandex Browser,
  Atom; `x86law-dev/ru-cert` installs the roots on Windows.

No single famous Reddit "RU НУЦ reverse proxy" recipe; the working pattern is the
standard nginx/Angie `proxy_ssl_*` plus the prebuilt roots.

## Extension points: wasm / external (checked in code)

Unit app types: `external`, `python`, `php`, `perl`, `ruby`, `java`, `wasm`,
`wasm-wc`. App modules load **dynamically** (`dlopen` + `dlsym("nxt_app_module")`
plus a discovery scan), but the ABI is for **application languages only** — there
is no loadable HTTP / proxy / TLS module ABI. So neither mechanism yields
upstream TLS:

- **`external`** — an out-of-process app. A **workaround**: the app fetches the
  HTTPS origin itself (trusting the НУЦ root) and returns the body; FreeUnit
  fronts it with client TLS. Core change 0, but `proxy_pass` semantics are lost.
- **`wasm` / `wasm-wc`** — a sandboxed WASI app (request/response only; no
  outbound network in the module). Not usable as a TLS client.

The clean fix is TLS-as-client inside the proxy module — the 1.38 TLS-module
direction.

## Site lists that serve the НУЦ root (third-party, checked 2026-10-15)

There is **no official registry** — Минцифры publishes only the CA certificates
and install guides (gosuslugi.ru/landing/crt, mos.ru/cert, sber, comss.ru).
Crowdsourced lists live on GitHub:

- **`CertIZDAT/russian-trusted-root-ca-analyzer`** (35 stars, default branch
  `master`): `dataset/government_domains.txt` — **21 237** government domains;
  `dataset/social.txt` — 363; `dataset/top-100.txt` — 101 (a traffic top list,
  not НУЦ-specific); `results/{government,social,top}/`; `statistics.db`
  (SQLite, 4.9 MB). README: **715** government sites *require* the Russian
  Trusted CA, **249** use self-signed.
- **`koenrh/russian-trusted-root-ca`** (7 stars): `tls_list_cleaned.txt` —
  **3 930** domains, plus the PEMs and CRLs.
- **`cocaman/russian_root_ca`** (4 stars): `tls_list.csv` (86 KB) and
  `tls_list2..5.csv` — **4 883** domains.

Samples (koenrh/cocaman — confirmed serving НУЦ): `komission.vtb.ru`,
`mgt.api.vtb.ru`, `cloud.sbermarketing.ru`, `transstroybank.ru`,
`webcon01.msk.vtb.ru`, `*.ingos.ru`, `online.mcbank.ru` (mostly banks).
Sample (CertIZDAT government): `minobr.nso.ru`, `budget.minfin-samara.ru`,
`soc.pskov.ru`, `artmuseum.karelia.ru`, `letters.bashkortostan.ru`.

Caveat: the data is dated 2020-2022 (headers `# 08.10.2022`, `# june 2022`), so
it has drifted; "requires НУЦ" != "only НУЦ".
