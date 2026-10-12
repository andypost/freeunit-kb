# FreeUnit 1.36.1 — rootless live test (Alpine, no root)

**Date:** 2026-09-11 · **Status:** DONE — unitd 1.36.1 + Python + PHP all serving live
requests on a non-root Alpine box.

## What was proven

Ran the **published** `freeunit 1.36.1` (Alpine edge/community) **without root**
and served real HTTP through all four paths:

| # | App | Port | Result |
|---|-----|------|--------|
| 1 | Python **WSGI** | 8801 | `hello from Unit wsgi.py` (py 3.14.7) |
| 2 | Python **ASGI** | 8802 | `hello asgi` |
| 3 | **X10 job-shim** (`job_asgi.py`) | 8803 | `{"job":"running"}` + supervised child restarts |
| 4 | **PHP** 8.4.25 | 8804 | `hello from Unit PHP`, `sapi=cli-server` |

Modules reported by `/status`: `python 3.14.7`, `php 8.4.25`.

## Packages used (all rootless, extracted to a user prefix)

- `freeunit-1.36.1-r0`, `freeunit-python3`, `freeunit-php84`, `freeunit-tools`
  (edge/community) — `unitd`, `python3.unit.so`, `php84.unit.so`, `unitc`.
- Deps pulled in: `libnjs` (unitd NEEDED), `php84-embed`+`php84-common`
  (`libphp.so`), `argon2-libs`, `libedit`, `libxml2`.
- `patchelf 0.18` (edge/main) to rewrite RUNPATH.

## The two blockers and their fix (rootless)

1. **`libnjs.so` missing** → unitd's own NEEDED. Fixed by extracting `libnjs`
   and setting `LD_LIBRARY_PATH` for the unitd launch (unitd resolves at exec).

2. **PHP module wouldn't dlopen** — `php84.unit.so` had a **hardcoded
   `RUNPATH=/usr/lib/php84`** (unwritable without root), and Unit **strips
   `LD_LIBRARY_PATH` for the discovery child**. Fix:
   - collect `libphp.so` + its deps into `/tmp/php84`;
   - **`patchelf --set-rpath /tmp/php84`** on **both** `php84.unit.so` and
     `libphp.so`;
   - restart → `module: php 8.4.25` loads.
   Python needed none of this: `python3.unit.so` has no RUNPATH and
   `libpython3.14.so.1.0` is already in `/usr/lib` (default musl path).

## Config gotchas found (code-grounded)

- **`spare` / `idle_timeout` are nested under `processes`**, not top-level:
  `"processes": { "spare": 1, "idle_timeout": 0 }`. Top-level →
  `"Unknown parameter \"spare\""` (atomic reject; whole config unchanged).
- **Unit requires a lifespan-aware ASGI app.** A naive ASGI app that ignores the
  `lifespan` scope throws `AssertionError: Got invalid state transition on
  lifespan protocol` on every request. Handling `lifespan.startup`/`shutdown`
  → 0 errors. (Python module advertises lifespan; must implement it.)
- Partial `PUT`s are order-sensitive: setting a `listeners/pass` before the
  referenced app exists fails; **one full-config PUT** is the robust path.

## X10 spike — live confirmation

`job_asgi.py` (the ASGI-lifespan job supervisor from the X10 spike) ran **inside
Unit**, spawned its child, and the child was **restarted on exit** (START/EXIT
pairs accumulating in `job.out`), while the app kept serving `{"job":"running"}`.
This validates the X10 "run long-lived jobs in the Unit runtime" primitive on a
real daemon — with `idle_timeout:0` + `spare:1` defeating the 15 s reaper.

## Reproduce (sketch)

```sh
# fetch apks into a prefix, extract (no root)
# unitd needs libnjs on LD_LIBRARY_PATH
patchelf --set-rpath <prefix>/php84 modules/php84.unit.so
patchelf --set-rpath <prefix>/php84 php84/libphp.so
unitd --control unix:/tmp/control.sock --modulesdir .../modules \
      --user $UID --group $GID --statedir ... --log ...
curl -X PUT --data-binary @config.json --unix-socket /tmp/control.sock \
     http://localhost/config
```

## Why this matters

- **FreeUnit 1.36.1 ships in Alpine** — a real distro-package signal; no build
  needed to test the released daemon.
- The **PHP RUNPATH** is a genuine **rootless/packaging friction** worth noting
  for Docker/rootless deploys (a module that hardcodes `/usr/lib/<lang>` breaks
  when the prefix differs). Relevant to X11 (modular TLS) packaging discussion.
- The **job-shim works on the real daemon** — X10 is not just theoretical.
