# zen-review PR #265 — php: give the module automount.language_deps mounts

_2026-09-08. Review of freeunitorg/freeunit#265 (OPEN, branch
`php/automount-language-deps`). Quorum DIVERGENT → resolved instrumentally via
tool-agent on the branch worktree. Approve to merge._

## What it fixes
PHP was the only language module declaring no mounts (`src/nxt_php_sapi.c`
`NULL, 0`), so an `isolation.rootfs` PHP app got nothing bound from host, while
Java/Python/Ruby each get their dirs. A PHP built with `--with-system-tzdata`
(Debian/Ubuntu/Fedora all carry it) reads the tz database lazily at request time;
Unit chroots the worker before `nxt_php_start()`, so the read resolves inside the
rootfs — missing db → distro patch derefs NULL → worker SIGSEGV on first `date()`.

## Root cause (verified)
Unit v1.36 vs PHP rootfs + system-tzdata: chroot happens before tz init, db must
be present in rootfs. Product half of #256. Design = `plan-php85-rootfs.md §4`.

## Mechanism
Mirrors `auto/modules/python`/`java`: `auto/modules/php` generates
`nxt_<module>_mounts.h`, build rule passes `-DNXT_PHP_MOUNTS_H`, `src/nxt_php_sapi.c`
includes it and wires `NXT_PHP_MOUNTS`/`NXT_PHP_NMOUNTS` into `nxt_app_module`.
Mount shape = Java jars: `NXT_FS_BIND, "bind", flags 0, builtin 1, deps 1` →
language dependency, so `"automount":{"language_deps":false}` opts out via the one
shared gate.

## Verdict: APPROVE
- ✅ Root cause correct (tzdb missing in chrooted worker).
- ✅ Design mirrors established language mounts (python/java), reuses shared gate.
- ✅ Fail-safe (see "quorum concerns closed") — author documented the trade-off.
- ✅ Files: `auto/modules/php` +304, `src/nxt_php_sapi.c` wired.

## Quorum concerns closed (tool-verified, branch worktree)
Blind quorum (muse + ling) returned PARTIAL because it had no diff. Instrumental
pass on branch `php/automount-language-deps` CONFIRMED the defenses the quorum
claimed were absent:
- `abs=trust`: path comes from the distro's build config (Fedora/Remi) — that IS
  the target package's build setting; comment `--with-system-tzdata` (line 284)
  explicitly trusts the build host.
- cross-host case: `auto/modules/php:412` — probe loop trusts build host to look
  like the rootfs.
- `a spurious mount beats a SIGSEGV`: line 292 — the mount-over-missing trade-off
  is deliberate (error toward mounting is safer than a crash).
- Sanitization: line 517 refuses control characters; relative paths refused
  (honest warning instead). Whitespace-path reconstruction warns.

## Notes
- Refs #256 (product half), `plan-php85-rootfs.md §4`.
- Test half covered separately; this covers the product mount.
