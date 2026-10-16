---
title: nginx vs freenginx vs Angie — measured code divergence
description: File-level comparison of the three nginx (web-server) forks — fork points, current divergence from upstream, and what each fork added or dropped. Measured against the GitHub mirrors.
tags: [nginx, freenginx, angie, forks, comparison, code, upstream]
status: analysis
updated: 2026-10-13
resources:
  - https://github.com/nginx/nginx
  - https://github.com/freenginx/nginx
  - https://github.com/webserver-llc/angie
---

# nginx vs freenginx vs Angie — how far the code has diverged

**Created:** 2026-10-13 by SOUL. Measured against the GitHub mirrors with a
partial (`--filter=blob:none`) clone, so **file-level** counts are real; line
counts were not captured (the promisor blob fetch failed). Facts are measured
unless marked *(reported)*.

> These are forks of **nginx** (the web server) — a different project from
> nginx/unit, FreeUnit's upstream. Kept as a fork-divergence / governance
> reference.

## Lineage

| | base | fork date | latest (measured) |
|---|---|---|---|
| **nginx** | — (upstream, F5) | — | `release-1.31.6` |
| **freenginx** | nginx **1.25.3** | 2024-02-14 | `release-1.31.4` |
| **Angie** | nginx **1.23.2** | 2022-10-26 | `Angie-1.12.2` (17 Sep 2026) |

- **freenginx** shares nginx's git history (nginx 1.25.3 SHA `b8fb83b8` is
  present in the freenginx mirror) → merge-base works. Maxim Dounin's fork after
  a governance/CVE-policy dispute with F5. Keeps the codebase, changes branding.
- **Angie** has **no shared git ancestry** with the nginx mirror (separate
  import), so merge-base is impossible — compare by tree. Ex-nginx-team fork
  (Web Server LLC / wbsrv.ru); "drop-in replacement". *(reported)* tracks nginx
  releases: README says "on top of nginx 1.31.2", CHANGES carry 23 "ported from
  nginx" entries.

## Governance & people (why they differ)

- **nginx** — owned by **F5** (commercial). Open-source core vs commercial
  **NGINX Plus**; some capabilities land Plus-first / Plus-only. **Fact:** the
  community **ingress-nginx** controller — the de-facto Kubernetes ingress — was
  **retired**: announced late 2025, maintenance ceased **March 2026**
  (kubernetes.io statement 2026-01-29; ~60% of clusters still used it at
  end-2025). The Ingress *API* stays; the NGINX *controller* is what retired —
  nginx itself is not retired. *Opinion* (maintainer): "features only for paid
  subscribers", regarded by the team as the weakest of the three.
- **freenginx** — **bus factor one**: Maxim Dounin's solo fork (a governance
  protest against F5's / CVE policy). No company, no team.
- **Angie** — company **"Web Server" (Web Server LLC, wbsrv.ru)**, founded by
  **ex-NGINX engineers** (~10 people, led by Valentin Bartenev; they maintained
  and developed nginx for ~10 years — nginx has belonged to F5 since 2019). They
  position Angie as "what nginx should have become" and also ship a commercial
  **Angie PRO**. *(reported)* the same Moscow team worked on nginx Unit.

## Measured divergence

**freenginx vs nginx** (`release-1.31.4` vs `release-1.31.6`):
- src files: nginx **426**, freenginx **406**.
- paths differing: **~312** — 4 added / 44 deleted / 264 modified.
- since the fork (2024-02-14): freenginx **354** own commits vs nginx **513**.
- The 44 "nginx-only" paths are mostly repo meta (`.github/`, `LICENSE`,
  `README.md`, `CONTRIBUTING.md`…) — freenginx is hg-based (has `.hgtags`). Code
  files nginx has that freenginx lacks (~13): `ngx_data.*`, `ngx_json*`,
  `ngx_siphash.*`, `ngx_event_openssl_cache.c`, `ngx_http_json_module.c`,
  `ngx_http_proxy_v2_module.c`, `ngx_http_tunnel_module.c`,
  `ngx_http_upstream_least_time_module.c`, `ngx_http_upstream_sticky_module.c`,
  `ngx_control.*`, `ngx_stream_pass_module.c`,
  `ngx_stream_upstream_least_time_module.c`.
- freenginx-only files: 4 — `.hgtags`, `docs/text/LICENSE`, `docs/text/README`,
  `src/mail/ngx_mail_limit_conn_module.c`.

→ **near-identical continuation:** same architecture, module system and config;
divergence = nginx's newer commits freenginx hasn't merged + branding.

**Angie vs nginx** (`Angie-1.12.2` vs `release-1.31.6`):
- src files: nginx **426**, angie **446**.
- paths differing: **~982** — **705 added** / 38 deleted / 239 modified.

→ **superset:** Angie keeps nginx and adds a large feature layer.

Angie-only source (new modules / core, measured):
- core: `ngx_acme.*`, `ngx_api.*`, `ngx_build.c`, `ngx_docker.*`, `ngx_dtoa.*`,
  `ngx_fiber.h`, `ngx_sticky.*`
- http: `ngx_http_acme_module.c`, `ngx_http_api_module.c`,
  `ngx_http_client_module.c`, `ngx_http_docker_module.c`,
  `ngx_http_doh_module.c`, `ngx_http_metric_module.c`,
  `ngx_http_prometheus_module.c`
- stream: `ngx_stream_acme_module.c`, `ngx_stream_metric_module.c`,
  `ngx_stream_mqtt_preread_module.c`, `ngx_stream_rdp_preread_module.c`,
  `ngx_stream_upstream_sticky_module.c`

*(reported)* Angie extras beyond nginx: RESTful JSON API + Prometheus/metric
zones, ACME, response-time-aware balancer, stream `slow_start`, NTLS via
Tongsuo, client-side HTTP/3, DoH.

## One-line answer

- **freenginx ≈ nginx** — same codebase, different governance; ~354 commits of
  independent drift, ~312 paths differ, structure identical.
- **Angie = nginx + a large feature layer** — ~982 paths differ, ~20 new src
  files, a whole new module set; tracks nginx as upstream.
- **nginx** is upstream and evolves on its own.

## Method / caveats

- Partial clones (`git clone --filter=blob:none --no-checkout`) of
  `nginx/nginx`, `freenginx/nginx`, `webserver-llc/angie`; file-level metrics via
  `git diff --name-status --no-renames` and `git ls-tree`.
- **Line counts not measured** — lazy blob fetch failed on the partial clone.
- Angie: **no shared git ancestry** with nginx → "since fork" commit counts are
  not derivable; use tree diffs.
- "files differing" between two live tips counts BOTH sides' evolution since the
  shared point, so it over-states a single fork's own changes.
- Versions move — re-measure the tags before quoting.
