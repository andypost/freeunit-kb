# zen-quorum — #323 durable-fix decision (case-sensitive `*.php` guard vs unfiltered `share`)

Date: 2026-09-13 · issue: freeunitorg/freeunit#323 (OPEN) · docs PR: freeunitorg/docs#28

## Question put to the field

Which durable fix for a case-sensitive `*.php` route guard in front of an unfiltered `share`?
Options: A docs-only sweep · B `share` refuses code media types unless opted in ·
C route matching follows the platform/filesystem case behaviour (nginx-style) ·
D allow-list of servable extensions in `share`.

Context block supplied (all verified in code at master `ad8f6936`): the `case_sensitive=1`
/ `PATTERN_NOCASE` uri rule with no config key against a deliberately `LOWCASE` host rule;
the case-insensitive MIME lookup; `share` serving anything reachable; removal of the `.php`
entry NOT being a fix (empty type makes `!application/x-httpd-php` match); a `types`
mismatch never resuming route evaluation; the `settings.PHP` 200 reproduction;
CERT VU#439395 and nginx trac #87 precedence; 14 docs pages carrying the guard with
only drupal carrying the false "denies any PHP scripts" claim; fork release policy
(patch = security/DoS only, behaviour change = minor).

## Run

Models (pinned from the live profile; `laguna`, `mimo`, `deepseek-v4-flash`, `nemotron*`
were DOWN): `ling-3.0-flash-fin-free`, `muse-spark-1.2-contributor-free`,
`muse-spark-1.3-contributor-free`. Window: **2 of 3** returned parseable claims.

| model | raw verdict | CONCLUSION | RISK | note |
|---|---|---|---|---|
| ling-3.0-flash-fin-free | `C` (prose: "most aligned with the context, especially points 1 and 6") | PARTIALLY-CLEARED | medium | verdict not printed — value longer than the 8-char clamp |
| muse-spark-1.2-contributor-free | `COMBO` | NOT-CLEARED | high | dissent: no single token is durable alone |
| muse-spark-1.3-contributor-free | — | — | — | no verdict registered |

muse-spark-1.2 reasoning: "No single token is durable alone because A leaves settings.PHP
200 on APFS/Docker, C alone still leaks if guard absent, and B/D alone leaves the
case_sensitive=1/PATTERN_NOCASE mismatch unfixed."

ling reasoning: matching "must follow filesystem case behavior with opt-in
case-sensitive matching, consistent with nginx precedent and the PATTERN_NOCASE root cause".

## Read

- Direction agreed: fix the COMPARISON, not the config — C. Plurality, not consensus.
- Divergence is on sufficiency, not direction: one vote (COMBO) says C does not cover the
  class where no guard exists at all, and B/D do not cover the mismatch. Both halves are
  checkable and both check out (see below).
- The field reads the docs-only option (A) as insufficient alone.

## Verification of the dissent's factual half (own code pass)

- "C alone still leaks if the guard is absent": confirmed by the docs sweep — `roundcube.rst`
  has no deny rule at all (its `*.php` entry is a pass-to-app rule), so on a case-insensitive
  filesystem an uppercase name reaches the share with nothing in front of it. `matomo.rst`
  by contrast DOES have a deny rule, and it works.

## CORRECTION (same day, code re-read)

An earlier version of this note claimed the `matomo.rst` rule
`["*.php", "*/.htaccess", "/config/*", "/core/*", "/lang/*", "/tmp/*"]` can never match,
because a `uri` array was read as an AND of its elements. **That is wrong, and the error is
inverted — treat the arrays as OR with exclusions:**

- `nxt_http_route_pattern_create()` sets `pattern->any = 1` for every element and zeroes it
  only for a `!` prefix (src/nxt_http_route.c).
- `nxt_http_route_test_rule()` early-returns when `pattern->any == ret`: a POSITIVE element
  short-circuits on SUCCESS, a NEGATIVE one on FAILURE. So positives OR together, and each
  `!` element excludes.
- `nxt_http_pattern_compare()` sorts negatives LAST, which only makes sense under that model.

Consequences: the matomo rule denies any of the six patterns as intended and is exposed to the
case vector exactly like drupal's; every `["*.php", "*.php/*"]` pair in the how-tos is correct;
and the new `/wp-content/*.php` step in docs#29 works (four positives OR together).
The surviving half of the dissent is the roundcube/no-guard case, which the matomo example does
not support.
- muse-spark-1.2's SPOT ("no diff/files touched to verify; single-token constraint is
  incomplete") is a meta-comment about the run shape, not a truncation red flag — expected
  for a design/text quorum. Its cited context point about the `.php` table entry is correct.

## Not decided by the quorum

The choice remains the maintainer's. What the quorum adds: a single-token answer is likely
wrong — pair C (match-time) with a sink-side half (B or D) if the intent is to cover configs
that never had a guard, and keep the docs sweep regardless, because it is the only part that
ships today.
