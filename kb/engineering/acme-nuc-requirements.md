# НУЦ (Russian National CA) ACME requirements + the acme.sh fix

Source: `acme_client_fix.rar` (Александр, 2026-10-14) = an **acme.sh 3.1.2** tree
plus `acme.sh_changes.docx` (НУЦ's change list). НУЦ = ИС НУЦ
(`nuc.voskhod.ru`), an ACME server issuing RSA **DV** certs, valid 90 days,
chained to the Russian Trusted Root CA.

## The seven changes НУЦ requires to acme.sh

1. **keyUsage extension** in the CSR: `digitalSignature,keyEncipherment`
   (required) + `keyAgreement` (optional) — `acme.sh:1261`.
2. **Subject `C=RU`** — the CSR subject carries `countryName=RU` —
   `acme.sh:1305-1313` (`openssl req -subj ".../C=RU"`).
3. **Renew period 85 days** — `DEFAULT_RENEW=85` (`acme.sh:70`), because НУЦ DV
   certs are valid 90 days.
4. **`idn` → `idn2`** — IDNA 2008 plus terminal-encoding fixes (`_idn()`,
   `acme.sh:1212`).
5. **Hide sensitive log data** — the POST body is hidden by default; `secure_debug`
   (hidden) / `insecure_debug` (plaintext) / unset (not logged); `--output-insecure`
   reveals it. `_secure_debug*` + `HIDDEN_VALUE` (`acme.sh:118,353,1938-1954`).
6. **`dns_regru.sh` cyrillic-domain fix** — unify full-domain / sub-domain
   formatting.
7. **`dns_regru.sh` log hiding** — `_post` hides the DNS API login/password.

НУЦ's own note: **any** ACME client works, provided its CSR matches НУЦ's
field/extension requirements.

## Assessment

- **All seven changes are CLIENT-side; none touches FreeUnit.** FreeUnit only
  receives the resulting bundle through `PUT /certificates/<name>`; the deploy
  hook is unchanged.
- **Two items are CSR requirements** (keyUsage, C=RU) and can be met **without
  patching acme.sh**: generate the CSR with `openssl req` (subject `C=RU`, a
  config carrying the `keyUsage` extension) and pass `acme.sh --issue --csr <csr>`.
  This keeps the client upgrade-proof.
- **The renew period** is acme.sh configuration (`Le_RenewalDays`), not a patch.
- **idn2 / log-hiding / dns_regru** are genuine acme.sh changes — check whether a
  current upstream acme.sh already carries them before vendoring the fork.
- Recommendation: **(A)** stock acme.sh + a custom CSR + `Le_RenewalDays=85` + the
  FreeUnit deploy hook (no fork); or **(B)** adopt НУЦ's build as-is. FreeUnit
  core: **no change**.
- Fits the `plugins.freeunit.org` catalog as a "НУЦ / acme.sh" entry — a hook +
  a recipe, not core.

## Prototype

The deploy hook + the recipe are in the workbench fork:
**`freeunitorg/freeunit-exp#51`** — `exp/acme-sh-nuc/acme-sh-freeunit-hook.sh`
(the hook) and `exp/acme-sh-nuc/README.md` (recipe), with
`docs/exp/acme-sh-nuc.md` (note). Path A: stock acme.sh + `--csr`. No core change.

## Related

- `engineering/acme-tls-plan.md`, `engineering/acme-certbot-thin-layer.md`
