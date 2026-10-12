# Release 1.37.0 — check of the release description

**Date:** 2026-10-04. **Ref:** tag `1.37.0` = `61b297ac` ("release: prepare 1.37.0",
04 Oct 2026); published on GitHub 2026-10-04T18:10:44Z. `version` = `NXT_VERSION=1.37.0`.
**Trigger:** "проверь описание релиза".

## Reproduced defect — the install commands in the release body 404

The GitHub release body (2087 chars, packaging text only) tells the reader:

```
DEB=1.37.0-1~trixie
curl -fLO "$BASE/freeunit_${DEB}_amd64.deb"
```

GitHub rewrites `~` to `.` in an uploaded asset name, so the stored name is
`freeunit_1.37.0-1.trixie_amd64.deb`. Measured:

- `.../download/1.37.0/freeunit_1.37.0-1~trixie_amd64.deb` → **404**, and `curl -f` exits 22
  (the copy-paste block fails at its second line);
- `.../download/1.37.0/freeunit_1.37.0-1.trixie_amd64.deb` → 200, 5 366 112 bytes.

The body's own prose acknowledges the rename ("the `.` in the asset file name is GitHub's
renaming of `~`") while the commands keep the `~` form.

**Worse, and older:** `SHA256SUMS` (both 1.37.0 and 1.36.1) lists the files with `~`
(11 lines), so `sha256sum -c --ignore-missing SHA256SUMS` matches nothing and silently
verifies nothing. Newer than 1.37.0 — 1.36.1's manifest has the same naming.

## The release description is missing the release notes

| release | body length | content |
|---|---|---|
| 1.37.0 | 2 087 | Debian trixie deb install instructions only |
| 1.36.1 | 16 043 | notes with sections + summary ("36 changes — 23 bugfixes…") |
| 1.36.0 | 10 220 | notes, security-first structure |

So 1.37.0 has no summary, no change list and no Security callout in the place an operator
looks first, while its CHANGES section holds 116 entries (16 of them Security).

## CHANGES ↔ docs/changes.xml divergence (one entry)

Block `ver="1.37.0"` in `docs/changes.xml`: 115 entries (bugfix 60, change 31, security 16,
feature 8). The CHANGES section: 116 (change 32). The extra entry is

> Change: a QUIT that fails because the worker already exited is now logged at the info
> level, not as an alert.

Token-compare of all other entries found no other divergence (the njs 1.0.1 and the
"upgrade contrib njs" wordings do match). Regeneration from the XML would drop that line
from the site changelog.

## Advisories

`/repos/freeunitorg/freeunit/security-advisories` lists two, both published 2026-07-17
(1.36.0 cycle). None for 1.37.0, whose 16 Security entries include request-reachable class
fixes (shared compressor stream between clients, unescaped access-log JSON values, the
route-regex ReDoS). Caveat: advisory drafts are not visible to the read-only token, so this
is "publicly none", not "none exist".

## Site

`freeunitorg/docs` (default branch `main`) last moved 2026-08-31 ("docs(release): 1.36.1
site update"): no 1.37.0 news entry and no CHANGES.txt section yet.

## Verified as correct

- version = tag = CHANGES header (04 Oct 2026) = GitHub `published_at` (04 Oct); no
  off-by-one date this cycle.
- Minor is the right bump: 8 Feature + 32 Change entries under the project's rule
  "patch = security/DoS fixes only".
- Changelog coverage of the window: 316 non-merge commits since 1.36.1, only 4 without a
  matching entry (three CI/test-only, one `Vary` tidy-up).
- CHANGES at the tag is identical to CHANGES on master.
- Spot checks against the code at the tag: `body_min_rate`/`send_min_rate` (default 0,
  "256 is a good value" — as written), `NXT_REGEX_MATCH_LIMIT` = 100 000 steps in
  `src/nxt_regex.h` (the entry itself states "at most 100 000" and names the pre-fix
  10 000 000), certificate `fingerprint` in `src/nxt_cert.c`, `--hardening=` in
  `auto/options`, cgroup-v2-aware default for `listen_threads`.
- Assets: 12 (core, php8.3/8.4/8.5, python3.13, `-dbg`/`-dev`, SHA256SUMS) — matches the
  module list the body offers.

## To fix

1. In the release body: `~` → `.` in the file names (or use `gh release download`); decide
   separately whether `SHA256SUMS` should carry the GitHub names.
2. Put the release notes into the release body (summary + sections, Security as its own
   callout).
3. Add the QUIT-logging entry to `docs/changes.xml`.
4. Decide the GHSA question for 1.37.0 before any announcement cites ids.
5. Update the site.
