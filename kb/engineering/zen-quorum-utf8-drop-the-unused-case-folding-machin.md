# zen-quorum: PR #314 — utf8: drop the unused case-folding machinery
_gathered 2026-09-12 · keyless OpenCode Free tier_

**PR:** utf8: drop the unused case-folding machinery
**Body:**
```
`nxt_utf8_casecmp()` was reachable only from the unit test and the basic fuzzer.
`nxt_utf8_lowcase()` only from `nxt_utf8_casecmp()` and from
`utf8_file_name_test`. And `utf8_file_name_test` exists solely to regenerate the
tables the other two read.

A closed loop: three symbols, two generated headers and a test binary that refer
only to each other, with nothing in the product reaching any of them. Unit folds
case with `nxt_strcasecmp()` / `nxt_memcasecmp()` — 22 call sites across 8 files —
everywhere it actually compares strings.

The cost of keeping it is not zero. The tables are generated from **CaseFolding
6.3.0**, which is 2013, twelve Unicode releases ago, by a generator whose path the
comment at the top of `nxt_utf8.c` has had wrong for years. Keeping the feature
honest would mean re-deriving them against a current release for something nothing
calls.

`nxt_utf8_next()` goes too. It is unreferenced anywhere in the tree, and it is
also wrong: its loop does `c = *p` before testing `p < end`, so on a buffer whose
last byte is a lead byte it dereferences one past the end before deciding to stop.
It is the helper someone would reach for to resynchronise after an invalid
sequence, so leaving a dead and out-of-bounds version of it in the header is worse
than having none.

`nxt_utf8_decode2()` loses its last caller outside the file and becomes `static`.

### Kept

`nxt_utf8_encode()`, `nxt_utf8_decode()`, `nxt_utf8_length()`,
`nxt_utf8_sanitize()` and `nxt_utf8_is_valid()`.

`nxt_utf8_is_valid()` is worth a note: it has **no caller on master**, which makes
it look like part of this removal. It is not — #312 adds its first production
caller, in configuration ingress validation. Verified against that branch before
removing anything.

### Measured

```
nxt_utf8.o   .rodata            12992 -> 0
             .data.rel.ro.local  4168 -> 0
             .text               1243 -> 987
unitd, stripped               559712 -> 543328   (-16384 bytes)
```

### Gates

- `./confi
```

## Opinions
- deepseek-v4-flash-free: FAIL (HTTP 400: {"error":{"type":"server_error","message":"Error from provider (Console): Upstream request failed: Model is unavailable.)
- **muse-spark-1.3-contributor-free** (33.7s): VERDICT=PARTIAL · CONCLUSION=PARTIALLY-CLEARED · RISK=low — unverified leftover references · CONFIDENCE=medium
- **muse-spark-1.2-contributor-free** (35.9s): VERDICT=PARTIAL · CONCLUSION=PARTIALLY-CLEARED · RISK=low — dead code removal only if grep claim holds · CONFIDENCE=medium
- mimo-v2.5-free: FAIL (HTTP 429: {"type":"error","error":{"type":"FreeUsageLimitError","message":"Error from provider (Console): Rate limit exceeded. Ple)
- **ling-3.0-flash-fin-free** (10.2s): VERDICT=CORRECT · CONCLUSION=CLEARED · RISK=none · CONFIDENCE=high
- **nemotron-3-ultra-free** (41.7s): VERDICT=CORRECT · CONCLUSION=CLEARED · RISK=none · CONFIDENCE=high
- **nemotron-3.5-lightning-free** (127.4s): VERDICT=CORRECT · CONCLUSION=CLEARED · RISK=none · CONFIDENCE=low
