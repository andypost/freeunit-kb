# FreeUnit Rust Toolchain Policy

**Created:** 2026-08-28
**Status:** POLICY — for the FreeUnit build
**Scope:** Rust crates in the FreeUnit tree and their MSRV/release tracking

---

## Why Rust is in FreeUnit — and why it's NOT an eol.json runtime

FreeUnit is primarily C, but ships three Rust components built at configure
time (`--otel`, `--wasm`):

| Crate | Path | Role |
|-------|------|------|
| `src/otel` | OTel SDK binding | spans, exporter (tokio, tonic, icu) |
| `src/wasm-wasi-component` | WASM runtime | component module |
| `tools/unitctl` | CLI tool | control-plane client |

**Critical distinction:** Rust is a **build-time toolchain**, not a runtime
version FreeUnit *serves*. eol.json tracks runtime versions FreeUnit executes
for user applications (PHP, Python, Go...). Rust does not belong there —
its lifecycle model is fundamentally different (see below).

---

## Rust release cycle — why there is no "EOL date"

Rust uses a **release train** (like Chrome/Firefox):

| Channel | When |
|---------|------|
| nightly | daily |
| beta | forks every 6 weeks |
| **stable** | **every 6 weeks, exactly** |

**There is NO LTS release branch.** Rust deliberately ships a new stable
every 6 weeks and does NOT backport security fixes to older minors — a CVE
is fixed by the *next* 6-week release, not by an LTS patch. Old stables keep
working via rustup but are not supported for fixes.

Therefore a "version dies on date X" mental model (PHP/Node eol.json entries)
does not apply. The right model is **MSRV** (minimum supported Rust version).

---

## Current state in FreeUnit

| Item | Value |
|------|-------|
| Rust editions | 2021 (all crates) |
| `rust-version` (MSRV) in Cargo.toml | **absent** |
| Pinned toolchain | `RUST_TOOLCHAIN: "1.88.0"` in build-deb.yml |
| Why 1.88 | `tonic 0.14 + icu 2.2` need rustc ≥ 1.88; Debian trixie apt rust is 1.85 |
| Current stable | **1.98.0** (2026-08-18) |
| Next major threshold | **1.100.0** (~2026-11-10) — edition 2024, deny-lints |

**Gap:** no rust-toolchain file, no MSRV declaration, no CI leg proving the
current stable (1.98) builds. Only the lower bound is exercised (1.88, in the
deb build), and only implicitly.

---

## Policy

### 1. Declare MSRV in every Rust crate

```toml
# src/otel/Cargo.toml, src/wasm-wasi-component/Cargo.toml, tools/unitctl/Cargo.toml
rust-version = "1.88"   # floor: tonic/icu dependency requirement
```

This is the "lower EOL" — the oldest toolchain FreeUnit supports building
with. Bump deliberately when a dependency raises its MSRV.

### 2. Test both edges in CI (bipolar)

```
MSRV (1.88)     → proves the floor still builds
current stable  (1.98.0) → proves the latest works
```

Add a small matrix leg next to the `openssl4` job in
`.github/workflows/build-test.yml`, or bump the existing `RUST_TOOLCHAIN` in
build-deb.yml and add a separate 1.88 leg.

### 3. Pre-empt the 1.100 threshold

The real breakage risk is not 1.98 (+10 minors, almost certainly fine) but
**1.100.0** (~2026-11-10): the edition 2024 migration brings new deny-by-
default lints and MSRV edges. Schedule a dedicated audit when it lands.

### 4. Do NOT add Rust to eol.json

eol.json semantics = "runtime version with a death date". Rust has none.
If visual tracking is wanted, keep it as a comment/variable, not a runtime
entry. The eol-check workflow assumes eol/supported_until dates, which Rust
does not provide.

---

## Decision matrix

| Question | Answer |
|----------|--------|
| Add Rust to eol.json? | ❌ No — wrong lifecycle model |
| MSRV `rust-version`? | ✅ Yes — `1.88` in each crate |
| Bump RUST_TOOLCHAIN to 1.98? | ✅ Low risk (1.36.2) |
| Audit for 1.100? | ✅ Required before 2026-11-10 |
| In 1.36.1? | ❌ Not now — post-tag, in 1.36.2 |

## Summary

- Rust is build-time, not a served runtime → not an eol.json concern.
- No LTS → track MSRV, not a death date.
- Floor today 1.88 (tonic/icu), current 1.98.0, watch 1.100 (edition 2024).
- Concrete actions: `rust-version = "1.88"`, bipolar CI legs, 1.100 audit.
