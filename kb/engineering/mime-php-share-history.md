# History: the `.php` MIME entry, the case-sensitive uri rule, and the share exposure

Traced 2026-09-13 from local clones (fork history carries upstream) + the GitHub API for the
archived `nginx/unit` and `nginx/unit-docs`. Purpose: settle the timeline in freeunitorg/freeunit#323,
which contains one wrong causal claim.

## Verified timeline

| date | commit / event | what it is |
|---|---|---|
| 2019-02-27 | `d4ccaae9` Igor Sysoev, "Initial routing implementation" | uri rule created `case_sensitive=1` + `PATTERN_NOCASE`; the **host** rule created `LOWCASE` in the SAME commit. The divergence is original, not accreted. |
| 2019-09-19 | `08a8d151` Valentin Bartenev, "Basic support for serving static files" | MIME lookup keyed with `nxt_djb_hash_lowcase` + `nxt_strcasestr_eq` → case-INSENSITIVE, in the same file whose route rule is not. |
| 2020-03-03 | `a98de7f7` | `fallback` for the `share` action. |
| 2020-06-29 | docs `1e53a8d2`, "Added Drupal to 'Howto/Applications'" | the Drupal how-to ships `["!/index.php*", "*.php", "*.php/*"]` → 404 with the hint "Explicitly denies access to any PHP scripts other than index.php". The `share` there is a **directory only** (`/path/to/app/web/`), no `$uri`. |
| 2021-05-06 | `b9d5eb28` Oisin Canty, "Static: implemented MIME filtering" | `nxt_http_route_types_rule_create()` → `case_sensitive=0` + `LOWCASE`. The two comparison functions now disagree inside one file. |
| 2021-05-26 | `81e31872` Oisin Canty, "MIME: added PHP." | one line: `.php` → `application/x-httpd-php`. No rationale in the message; shipped in 1.26.0. |
| 2021-09-30 | `c5220944` Zhidao HONG, "Static: variables in the \"share\" option." | makes `"share": "/path$uri"` possible. |
| 2021-11-18 | docs `57480b1f`, "Updated share, chroot usage info" | the Drupal how-to adopts `$uri` in the share. **From here the bypass serves an arbitrary reachable file.** |
| 2024-01-20 | nginx/unit#1079 (mqudsi) | `index` in `share` bypasses `types` — a DIFFERENT mechanism (index is not type-filtered). |
| 2024-01-21 | nginx/unit#1080 (alejandro-colomar), "Honor (MIME) `types` in `index`" | fix attempt, blaming regression `c5220944`. Closed unmerged. |
| 2024-01-24 | #1079 closed by tippexs, "not a bug" | VBart ruled it intentional: "Serving PHP sources is an issue only if a user had no intention to do so"; cites the documented "If a share path specifies only the directory name, Unit doesn't apply MIME filtering" (still present in the reference). alejandro withdraws the behaviour change, keeps only the NUL fixes (#1086). |
| 2025-10 | nginx/unit `76b39e92`, nginx/unit-docs `bc8c05ea` | archived; the docs repo's last commit is the archival notice. |
| 2026-06-11 | fork `68f079b6` | the fork adds the explicit comment on the host `LOWCASE` rule ("no per-rule sensitivity flag") — the fork documented the ADJACENT line without touching uri case sensitivity. |
| 2026-07…09 | fork static routing commits | templated-share NUL rejection, router-thread freelist drain, truncation handling, Last-Modified in GMT, `nxt_time_t` width. This area is actively maintained here. |

## Upstream search result (issue search API, archived repo)

- `"case-insensitive"` / `"case insensitive"`: **0 hits** anywhere in nginx/unit issues+comments.
- `"x-httpd-php"`: **1 hit** — #1079, which decided the index question and never mentions case.

So #323's claim that the case vector was never raised upstream is confirmed independently.

## Correction to #323's timeline (the issue's own causal sentence is wrong)

The issue states: "The 2020 annotation was true when it was written. `.php` had no media type
until 2021, so a `share` reaching a PHP file did not serve its source. A one-line MIME addition
invalidated a security claim written eleven months earlier."

Wrong on the mechanism, as #323's own later section proves: an unfiltered `share` returns the
bytes whatever the extension — with no MIME type the file is served with no `Content-Type`
header, not withheld. What actually changed the *documented* config's reachability is the
adoption of `$uri` in the Drupal share (`57480b1f`, 2021-11-18, three weeks after `c5220944`),
because until then the shipped share was a bare directory.

The annotation was therefore false from the day it was written — the uri rule has matched
case-sensitively since 2019-02, in the same commit that made the host rule case-insensitive.
The 2021 MIME entry did not create the leak; it added the LABEL and made the
`!application/x-httpd-php` filter expressible at all. Consequences for the write-up:
- The MIME entry is neither the cause nor a candidate fix; #323 already reached this, and now
  the earlier section should be corrected so the two halves stop contradicting each other.
- VBart's 2024 "intentional" ruling answered the INDEX question, not the case vector, which was
  never put to the project. It is not precedent for this report — as #323 says, but the
  precedence argument is stronger once the timeline is right.
- The severity argument should stand on the 2021-11 documentation date, not on 2021-05.
