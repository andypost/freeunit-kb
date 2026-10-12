# Evolver (andypost/evolver-php) — cross-version static analysis reference

_2026-09-04. Reference project: how to make code reading FAST and PRECISE via
tree-sitter → symbols → SQLite, instead of semantic/vector search. This is the
pattern to replicate for FreeUnit (C), unitctl, and php-src — and it is what the
reference for reading code faster and more exactly than context guessing._

## What Evolver is

A PHP 8.5 CLI (Symfony Console) + Amp web UI that uses **tree-sitter via FFI** to
analyze Drupal core across git version tags:

1. **index** — parse all PHP/YAML files with tree-sitter, extract symbols
   (functions, classes, methods, services, routes, permissions) into SQLite
2. **diff** — compare two indexed versions; detect removals/renames/signature
   changes/new deprecations; generate a tree-sitter query pattern per change
3. **scan** — run those patterns against your code; report matches + severity
4. **apply** — mechanical fixes (renames, param inserts, service renames)

## Why this beats vector (Qdrant) for CODE

- Code is STRUCTURE, not semantics. You want an exact answer ("who calls X, what
  does X depend on"), not a fuzzy similarity.
- Symbol extraction into SQLite gives **O(1) exact retrieval** by fqn / name /
  signature-hash, plus **set-diff** across versions (EXCEPT is 35% faster than
  NOT EXISTS for this).
- tree-sitter is **error-tolerant** — works on real code with macros/includes
  (pycparser, a strict AST, failed the whole unit codebase: 0/141 files).
- This is authoritative for the earlier conclusion: **Qdrant = wrong tool for
  code (CPU/RAM, low precision); tree-sitter + SQLite = right tool (exact, cheap).**

## Architecture (to mirror in Python)

```
CLI  index|diff|scan|apply|report|status|query
  └─ Service layer  CoreIndexer  VersionDiffer  ProjectScanner  Applier
       └─ Parser(FFI)  Extractor(PHP/YAML)  PatternMatcher
            └─ SQLite Storage  versions|files|symbols|changes|matches|snaps
```

## Key storage decisions (copy these)

- **SQLite 3 WAL mode**, foreign keys on, parameterized queries (no injection).
- **signature_hash = SHA-256(type|fqn|params|return_type)** → O(1) diff vs O(n).
- **JSON1**: `json_extract()` server-side filtering 2-6x faster than PHP-side decode.
- **EXCEPT** for set-difference (35% faster than NOT EXISTS).
- **Covering index** `idx_sym_version_fqn_type_hash` → index-only scans for
  signature changes.
- **weight** column = `major*1e6 + minor*1e3 + patch` → quick upgrade-path queries.
- **Batch inserts** for bulk writes; **prepared-statement caching** in tight loops.
- **Surgical text replacement** by byte offset, applied **bottom-up** (highest
  offset first) to preserve positions. No AST→source round-trip.
- **Multi-process**: `pcntl_fork` for parallel index/scan; workers extract, parent
  merges into SQLite (avoid lock-heavy shared writes). FFI/Parser are process-local,
  recreated after fork.
- **FTS5** (available, we verified) could also index the symbol/body text for a
  content fallback when an exact symbol is unknown.

## Symbols table (MVP subset — the core)

```
symbols(id, version_id, file_id, name, fqn, symbol_type, parent_symbol,
        signature_hash, is_deprecated, ast_node_sexp, ast_node_json, source_text)
CREATE INDEX idx_sym_fqn        ON symbols(fqn);
CREATE INDEX idx_sym_hash       ON symbols(signature_hash);
CREATE INDEX idx_sym_deprecated ON symbols(is_deprecated) WHERE is_deprecated=1;
CREATE INDEX idx_sym_file       ON symbols(file_id);
CREATE INDEX idx_sym_parent     ON symbols(parent_symbol) WHERE parent_symbol IS NOT NULL;
```

## Gotchas learned in Evolver

- **FFI types are instance-scoped** — use `$ffi->new()` not `FFI::new()` (types
  only exist on that FFI instance). For Python this is less of an issue; tree-sitter
  python bindings are the wrapper.
- **tree-sitter CLI on Alpine doesn't load external grammars** — use the FFI/library
  path, not the CLI. (For Python we use the `tree-sitter` + `tree-sitter-c/php`
  wheels, which work — verified on unit: 1935 funcs / 1605 calls in 0.9s.)
- **Node::walk() named children only** to avoid infinite recursion on unnamed nodes.
- **#[\NoDiscard]** on methods returning values you must use (use (void) to drop).

## In KB context

Replaces the "Qdrant for code" non-starter with an exact-symbol pipeline. Used by:
- an agent reading code → faster and more exactly (index unit + php-src symbols, query by fqn).
- FreeUnit → cross-version breaking-change detection (Drupal-style diff).
- Sofar we verified the PYTHON path works: `tree-sitter-c` parses unit (1935 defs /
  1605 calls in 0.9s), error-tolerant vs pycparser's 0/141.

## Related
- `engineering/unit-code-graph.md` (planned) — Python tree-sitter symbol index for unit.
- `engineering/ops-environment-facts.md` — no gcc/ctags; use tree-sitter via uv.
