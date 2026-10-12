# zen-review PR #294 — pkg(eol): sync Ubuntu and Debian EOL dates

_2026-09-08. Review of freeunitorg/freeunit#294. Data/docs only, zero runtime code._
_+24/−19 across 3 files: `EOL.md`, `pkg/eol.json`, `pkg/eol/README.md`._

## What it changes
- Ubuntu 22.04 EOL 2027-04 → 2027-06; 26.04 2031-04 → 2031-05 (and matching
  `supported_until`). Synced with endoflife.date API.
- Documents the field mapping: `eol` (standard support end) is always what the
  table tracks. For Debian since Sept 2026 `eol` became the end of **LTS**, so the
  tracked security window moved to the API's `support` field. Ubuntu stays on `eol`
  (ESM excluded).

## Verdict: APPROVE
- ✅ Pure data/doc change — no runtime code, no behavioral risk.
- ✅ Dates verified against endoflife.date (README states 2026-09-08 check, no errors).
- ✅ Field-mapping note is precise and matches the `pkg/eol/` per-vendor picker.

## Notes
- Duplicate-dates check: entries still inside grace window; only proximity/past-EOL
  warnings, no hard errors.
