# --hardening: configure mechanics and measured behaviour (PR #444)

Reviewed at head `3bb54805f22e` (build/hardening), 2026-09-26. All numbers below are
from executed runs, not from reading.

## How the flag reaches the build

- `auto/cc/hardening` is sourced from `configure` right after `auto/cc/test`; the whole
  block is inside `if [ $NXT_HARDENING != off ]`, so the default build is untouched.
- Each compiler flag is probed by compiling `$NXT_CFLAGS $flag $NXT_CC_OPT $CFLAGS -Werror`
  (same order as `auto/make`'s `CFLAGS = $NXT_CFLAGS $NXT_CC_OPT $CFLAGS`), each linker flag
  by linking a trivial program with `$NXT_LD_OPT $flag`.
- Linker flags are probed with `-Wl,--fatal-warnings` (itself probed first), because GNU ld
  only warns about an unknown `-z` keyword and still exits 0. The fatal-warnings flag is used
  for probes only, never appended to `NXT_LD_OPT`.
- `NXT_LD_OPT` is consumed by `auto/make`: `NXT_EXEC_LINK` (unitd, modules, test binaries) and
  `NXT_SHARED_LOCAL_LINK` (libnxt.so). Verified end to end in the generated Makefile.
- `set +e` around the probes, `set -e` after: `auto/cc/test` does the same (its line 152), so
  errexit is restored identically in every mode — no mode-dependent error semantics.

## Measured (musl-gcc 11.2.1, GNU ld 2.37, x86_64)

- `--hardening=off` vs an unoptioned build of master: `CFLAGS` line identical, generated
  Makefile differs only by the new test object. The "no change unless asked" claim holds.
- `--hardening=default` lands `-fstack-protector-strong -fstack-clash-protection
  -fcf-protection -D_FORTIFY_SOURCE=3` plus `-z relro -z now -z noexecstack` in the link
  recipes; `-mbranch-protection=standard` is correctly rejected on x86_64.
- `--hardening=strict` adds `-Wformat=2 -Wvla -Wimplicit-fallthrough`; with GCC 11
  `-ftrivial-auto-var-init=pattern` is correctly skipped (GCC 12+ flag).
- Strict vs default, 162 sources the Makefile lists, compiled with the real flags and the
  in-tree `-Werror`: **identical outcome, zero new failures.** So the 17 `nxt_fallthrough`
  sites and the remaining `/* Fall through. */` in `nxt_epoll_engine.c` (blank line before the
  label, GCC's default comment heuristic) warm nothing, and `-Wformat=2`/`-Wvla` are quiet.
- Invalid or empty `--hardening=` value: `configure` exits 1 with `invalid value ... Valid
  values are: off, default, strict`.
- Fortify probe semantics:
  - `--cc-opt=-O0` (and `CFLAGS=-O0`): both `=3` and `=2` report "not found" — the probe's own
    `#ifndef __OPTIMIZE__ / #error` fires, so FORTIFY is skipped rather than misreported.
  - libc whose headers warn at level 3 (simulated with a `#warning` shim on the include path):
    `=3 ... not found`, `=2 ... found`, and `NXT_CFLAGS` carries `=2`. The fallback works.
- On Linux the `_FORTIFY_SOURCE` part is inert for core objects: `src/nxt_unix.h` `#undef`s it
  before the libc headers (pre-existing behaviour, unchanged by the PR). The flag still
  reaches the link recipes and the compiler-level protections are unaffected.

## Gaps worth one line

- No CI leg builds with `--hardening`; the whole path is exercised by hand only.
- `auto/help` advertises `_FORTIFY_SOURCE` without the `nxt_unix.h` caveat.
