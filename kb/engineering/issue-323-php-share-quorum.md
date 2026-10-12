# freeunit#323 — `.php` in the built-in MIME table vs a mis-ordered `share`

_Quorum run 2026-09-12 (keyless OpenCode Free tier) + my own code pass. Issue still OPEN._

## The finding

`src/nxt_http_static.c` maps `.php` → `application/x-httpd-php` in the default MIME
table. A `share` action serves any file it can reach, so a configuration whose `share`
step is not preceded by a rule rejecting `*.php` serves `sites/default/settings.php`
(DB credentials, `hash_salt`) as a 200 with a normal-looking content type. In the
published Drupal example the protection is the single ordering line
(`"!/index.php*"`, `"*.php"` → 404) ahead of the share — **not** the 32-pattern deny
list, which never covers `*.php`.

## Quorum (INLINE, choices A|B|C|D)

Window 7, registered verdicts 1 — report it as the field's lean, not as consensus.

- `ling-3.0-flash-fin-free` → **B** (12-14s), the only parseable verdict.
- `muse-spark-1.2/1.3-contributor-free` → prose only ("ordering-dependent documentation
  is a fragile contract; dropping the MIME entry only relabels the leak"), 33-41s,
  no VERDICT line (opinion not registered).
- `nemotron-3-ultra-free` → prose only, same direction (no in-engine defense-in-depth;
  configuration-only guards are missed by first-principles configs).
- `deepseek-v4-flash-free` 400 (model unavailable), `mimo-v2.5-free` 429 (quota),
  `nemotron-3.5-lightning-free` 180s timeout. Not dissent — no vote.

A: close as documentation-only · B: engine change in the next minor, `share` refuses
php-family extensions by default with an opt-in · C: drop the MIME entry and close ·
D: not-a-bug.

## What the quorum missed, and what the code says

1. **C is worse than "cosmetic" and should be rejected.** With no entry for `.php`,
   `nxt_http_static_mtype_get()` returns an empty type, and
   `nxt_http_route_test_rule()` XORs the match with `pattern->negative`: the negated
   pattern `!application/x-httpd-php` then **matches** an empty subject and the share
   starts *serving* the file it was configured to block. Dropping the entry therefore
   neuters the only in-engine filter operators have. `test_static_types_fallback`
   (test/test_static_types.py) is the guard that would fail.
2. **The intermediate mitigation already exists and is tested.** `types:
   ["!application/x-httpd-php"]` on the share — same test, with a fallback proxy. Note
   the caveat the docs now carry: a `types` mismatch does **not** resume routing, it
   takes the share's fallback or 403 (`nxt_http_static_next()`), so as a fix for a
   reordered Drupal config it costs `install.php`/`update.php` their `direct` target.
3. **B needs a defined extension set.** The table knows only `.php`; `.phtml`,
   `.php3/4/5`, `.phar`, `.phps` are not in it, so "php-family" has to be spelled out
   (and `.phps` — source meant to be displayed — is the case that argues for an opt-in
   rather than a hard refusal).
4. Docs PR freeunitorg/docs#28 was still open at the time of the run (its premise
   question), and by release policy a behaviour change like B lands in a **minor**, not
   a patch.

## Coordinator position

Keep #323 open as the engine item (B, next minor), label it (`z-bug`, `z-c`), and let
the docs PR carry the immediate exposure. Reference the `types` pattern in the issue as
the supported interim workaround, with its fallback caveat attached.
