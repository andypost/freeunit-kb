# NXT_TESTS hooks: per-object macro in two archives (PR #413)

Reviewed at head `75610082fd14` (build/one-pass-test-archive), 2026-09-26. Facts below are
from the CI run on that head (`c-tests` job, step "Check the test hooks are in the test
programs only") and from the diff, not from the PR prose.

## The mechanism

- `--tests` no longer calls `auto/have`, so `NXT_TESTS` is absent from
  `build/include/nxt_auto_config.h`. It is a per-object macro now.
- `auto/make` compiles every source of `NXT_LIB_SRCS` and `NXT_LIB_UNIT_SRCS` a second time
  with `-DNXT_TESTS=1` into `<name>.test.o`, and archives them as `libnxt-tests.a` and
  `libunit-tests.a`. Sources under `src/test/` are compiled with the macro. Every test
  program links the `-tests` archives only.
- `unitd`, `libnxt.a`, `libunit.a`, `build/src/nxt_unit.o` (the object the language modules
  link) and all `*.unit.so` come from the plain objects. Without `--tests` nothing extra is
  compiled and the generated rules only gain an empty variable.
- `NXT_LIB_UNIT_TEST_OBJS` also names four core objects explicitly (`nxt_lvlhsh.c`,
  `nxt_murmur_hash.c`, `nxt_socket_msg.c`, `nxt_websocket.c`) so that libunit test programs,
  which link `libunit-tests.a` alone, are self-contained. All four are in `NXT_LIB_SRCS` too,
  so the object is deliberately in both archives. This is the only hand-maintained list left;
  a missing core dependency fails at link time (loud), not silently.

## The gate

`.github/scripts/check-test-hooks.sh`, run in the `c-tests` job between "Build C tests" and
"Run C tests". It keeps no list: hook symbols are the names defined in `X.test.o` and not in
`X.o`, dot-containing compiler clones skipped. It fails (exit 1, `::error::`) when

- `NXT_TESTS` is in `nxt_auto_config.h`, or `.test.o` files are missing, or the derived hook
  set is empty (these three are the anti-vacuous guards — an empty set is a FAILURE);
- a source outside `src/test/` mentions `NXT_TESTS` in a preprocessor directive but has no
  `.test.o`, or its plain and instrumented objects are identical after `objcopy --strip-debug`;
- `unitd`, `libnxt.a`, `libunit.a`, `nxt_unit.o`, `libnxt.so` or any `*.unit.so` defines a
  hook symbol;
- a test program that linked object X does not define X's hooks (it took the plain copy).

Names that another plain object also defines are printed and excluded from check 2 (a static
that one compile inlines); the script argues the leak they could hide is caught by the
macro-in-config-header guard instead.

## Measured on the head

- The gate prints `hook symbols: 47` and `ok: hooks are in the test programs only`. The PR
  body says 43 symbols (28 core + 15 libunit) — a source-level count; the derived set is a
  superset because it also picks up statics that only one of the two compiles keeps.
- Census at the head: 10 core/libunit sources carry 22 `#if (NXT_TESTS)` directives, plus 9
  internal headers (and `src/nxt_unit.h`, the public one) with declarations. Matches the body.
- `pkg/deb/Makefile:172` and `pkg/rpm/Makefile:145` pass `--tests`, and have since the 2017
  packaging commits (`156877f3`, `eabe25d9`) — that commit is contained in 98 tags, oldest
  `0.2`, newest `1.36.1`, i.e. the released debs and rpms carried the hooks until this lands.
