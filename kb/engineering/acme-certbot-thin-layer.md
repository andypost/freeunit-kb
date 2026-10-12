# ACME via certbot thin layer for Unit — the "прослойка"

**Date:** 2026-09-11 · **Status:** built + tested live on running unitd 1.36.1
**Artifacts:** `tools/artisan_stubs/certbot-unit-hook.sh` (+ generic `acme_stub.py`)
**Verdict:** ✅ correct call — certbot as-is + a ~40-line Unit hook beats a
hand-rolled ACME client.

## Why a thin layer, not our own ACME

certbot already owns **all** the hard ACME parts: account/registration, JWS
signing, nonces, challenge orchestration, ordering, renewal bookkeeping, staging
vs prod, rate-limit handling. Reimplementing that is months of churn for nothing.

Unit only needs **two** pieces of glue, both trivial and Unit-specific:

1. **HTTP-01 challenge serving** — certbot's `--webroot` writes a token to
   `<webroot>/.well-known/acme-challenge/<tok>`; Unit serves it with **one route**.
2. **Deploy** — certbot's `--deploy-hook` calls our script with the renewed
   lineage; we `PUT` the bundle to the **Control API**.

That is the whole "прослойка". No ACME in C, no TLS-ALPN-01 work needed for the
common case.

## What was tested live

| Half | Test | Result |
|------|------|--------|
| **Deploy hook** | fake lineage → `certbot-unit-hook.sh` → live unitd | `hook: deployed hookcert ... to Unit`; `GET /certificates/hookcert` → **CN: hook.example.com** ✅ |
| **HTTP-01** | token in webroot → fetch over HTTP like the ACME server | route `/.well-known/acme-challenge/*` → `share: <webroot>$uri` → **`TOKEN-CONTENT`** ✅ |

certbot itself: `5.8.0` (Alpine edge, or `uv pip install certbot`); hook flags
`--deploy-hook` / `--pre-hook` / `--post-hook` / `--webroot` all present.

## The hook (essence)

```sh
# certbot renew --deploy-hook /usr/local/bin/certbot-unit-hook.sh
LINEAGE="$RENEWED_LINEAGE"                 # /etc/letsencrypt/live/<domain>
cat "$LINEAGE/privkey.pem" "$LINEAGE/fullchain.pem" > "$TMP"
curl -sS -X PUT --data-binary @"$TMP" --unix-socket \
     "${UNIT_CONTROL_SOCK:-/var/run/control.unit.sock}" \
     "http://localhost/certificates/${UNIT_CERT_NAME:-$(basename "$LINEAGE")}"
```

Key Unit-side facts:
- The certificate object wants **privkey + full chain in ONE PEM** (concatenate).
- A `PUT` to an **existing** name replaces the cert and triggers the reload —
  **no restart, no delete-then-add "dance"** (this is the upstream #195 pain; our
  X9 Step 1 makes it unnecessary).
- `$uri` in a Unit route is the **full** request path → the webroot share must be
  `"<webroot>$uri"`, not `"<webroot>/.well-known/acme-challenge$uri"` (the latter
  double-prefixes → 404).

## Wiring (turnkey)

```sh
certbot certonly --webroot -w /var/www/acme -d example.com \
        --deploy-hook /usr/local/bin/certbot-unit-hook.sh
# renew timer (cron/systemd) -> certbot renew (hook fires only on real renewal)
```

Unit config (the challenge route + the TLS listener that uses the cert):

```json
"listeners": { "*:443": { "tls": { "certificate": "hookcert" }, "pass": "routes" } },
"routes": [ { "match": { "uri": "/.well-known/acme-challenge/*" },
              "action": { "share": "/var/www/acme$uri" } } ]
```

## Two integration shapes (both valid)

1. **External certbot + OS timer** (this doc) — simplest; certbot renews via
   cron/systemd, hook deploys. No Unit app at all.
2. **certbot driven from the Unit app** (`acme_stub.py`, X10 pattern) — the app's
   `lifespan.startup` loop runs `ACME_CMD`/certbot and deploys; makes Unit
   self-driving (no host cron). Use when you want zero external schedulers.

Both share the **same hook logic** and the **same config route**. Start with (1);
move to (2) if you want the daemon self-updating.

## Caveats

- **HTTP-01 only** here (works today, no X11). **TLS-ALPN-01** still needs the
  modular-TLS work (select cert per ALPN in-handshake) — see `acme-reuse.md` Step B.
- certbot's own `--deploy-hook` does **not** fire on `--dry-run` unless
  `--run-deploy-hooks` is passed (good for prod safety).
- Rename/repoint a cert in Unit by re-`PUT`ting the name; retire the old one only
  after the new is live (atomic swap).
- Account key + lineage are **secrets** — live under `/etc/letsencrypt`, never in
  Unit config.
