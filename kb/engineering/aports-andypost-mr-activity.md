# andypost — aports GitLab MR activity (2026-09-03)

_Author `andypost` on `gitlab.alpinelinux.org/alpine/aports`. Total **100+ MRs**,
mostly merged. Snapshot of OPEN state below._

## Open (not draft) — ready for merge attention, 2
| MR | title | updated |
|----|-------|---------|
| !107657 | [3.24] community/freeunit: upgrade to 1.36.1 | 2026-08-31 |
| !107633 | */php8?-pecl-grpc: upgrade to 1.83.1 | 2026-08-31 |

## Draft (in progress), 7
| MR | title | updated |
|----|-------|---------|
| !104906 | */php8?-pecl-xlswriter: upgrade to 3.0.0 | 2026-08-30 |
| !106897 | community/uv: upgrade to 0.12.5 | 2026-08-29 |
| !106909 | testing/php86-pecl-*: new aport | 2026-08-17 |
| !105133 | main/quickjs-ng: upgrade to 0.15.1 | 2026-08-10 |
| !101711 | main/gcc: upgrade to 16.2.0 | 2026-08-08 |
| !100779 | community/php85-pecl-decimal: upgrade to 2.0.2 | 2026-05-15 |
| !90243 | community/unit: enable OTEL and add unitctl | 2025-10-16 |

## Themes (from the merged set)
- **PHP maintenance is the backbone**: php81..php86 upgrades (master + 3.22/3.23/3.24 stable
  branches), pecl-* bumps (brotli, zstd, xdebug, grpc, mongodb, swoole, timezonedb, redis,
  apcu, xlswriter, pcov, spx, decimal), php86 new aports + many rebuilds against each alpha/beta.
- **FreeUnit packaging**: community/freeunit 1.36.0 → 1.36.1 (+ 3.24-stable), testing/freeunit-php86
  rebuild against php 8.6.0_beta1. The bot's own packaging — mirrored from the FreeUnit release cadence.
- **Cross-language upkeep**: uv, composer, openldap, postfix, sqlite, quickjs/quickjs-ng,
  ctranslate2, py3-charset-normalizer / -typeguard / -bracex / -jwt / -treq / -openssl / -oci,
  main/gcc (draft — a big one).
- The `community/unit: enable OTEL + unitctl` draft (2025-10) is the Nginx-Unit lineage carryover.

## How to re-snapshot
```bash
GITLAB_HOST=gitlab.alpinelinux.org glab api \
  "projects/alpine%2Faports/merge_requests?state=opened&author_username=andypost&per_page=100"
```
Filter `draft` vs `opened` in python (draft bool). Implies keyless public access — no token.
