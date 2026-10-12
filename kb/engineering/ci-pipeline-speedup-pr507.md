# Build & Test pipeline speedups (PR #507)

Reviewed at head `cc4df8ea4442` (ci/speedup-pipeline), 2026-09-27. Numbered items are the PR
body's. Timing facts below are the GitHub job timings of run 36322425869 (this branch) compared
with run 36318226905 (PR #448, the run the PR measures against), not the PR's own table.

## Items

1. `prepare` reorders the matrix: python, wasm-wasi-component, java, php, unit, perl, wasm, go,
   node, ruby. Both jq expressions were re-run on `pkg/eol.json`: 23 legs each, identical sets.
   The start order in the run cannot show the intended effect - the legs started in an order
   matching neither list (php-8.3 first, all three python legs last). That run was queue-bound:
   `prepare` started 5 min after the run started and `core` 13 min, so its 39.5 min wall is not
   comparable with the 12.0 min baseline.
2. `recvall(framed=True)` in test/unit/http.py stops as soon as `_response_complete()` sees a whole
   response. Verified from the job timings: every leg is 40-100 s shorter (python-3.12 372->270,
   ruby-3.4 126->49, php-8.4 255->189, node-22 154->84, java-25 273->211, wasm 88->38, perl
   109->57, unit 223->212; java-26 224->228 is the only leg that grew).
3. Python shards balanced by measured time: legs went 372/283/231 s -> 270/289/280 s (the body
   predicted 227/241/216 pytest time; leg time is pytest plus about 40 s of setup).
4. `core` caches `~/.cargo/registry`, `~/.cargo/git`, `src/otel/target`.
5. `wasm-wasi-component` caches the same three paths for its own crate, and sets
   `CARGO_INCREMENTAL=0`.

Both new caches were saved by the first run (caches API: `otel-cargo-Linux-X64-rustc-1.98.1-...`
109 MB at 13:41:19, `wasm-wasi-component-cargo-...` 322 MB at 13:59:28), so a hit is unproven
until a second run - the body says this. Nothing in the workflow wipes a restored target (no
`git clean`, no `make clean`). The keys do not collide with the existing
`{os}-{arch}-cargo-{hash}` cache used for `test/fake_upstream` and `test/fake_otlp`.

## `_response_complete()` - why it is safe

It returns True only for a response whose own framing says it is whole (Content-Length reached, or
chunked with a `0` chunk and its CRLF). Everything else - no Content-Length and no chunked, a
Content-Length it cannot parse, chunked with trailers, a coding list that only ends in `chunked`
(it uses `value.lower().endswith(b'chunked')`), and any bodyless response (HEAD, 1xx, 204, 304,
which it documents as out of scope) - returns False, and the read then ends on `read_timeout`
exactly as before. A body that is short of its declared Content-Length never looks complete, so
the helper cannot hide a truncated response; it only skips the wait when completeness is provable.

## The shard guard

`if [ "${#owner[@]}" -ne "$n" ]` fires when a shared file has no owner or two files collapse onto
one key, i.e. it is a duplicate/omission net inside one leg. The property "each shared file is in
exactly one shard across the three python legs" holds by construction instead: all three legs
derive the same map because `versions = length(.runtimes.python)` and
`shard = index of this leg's version` come from the same `pkg/eol.json`, and the assignment loop is
deterministic. The heavy-file weights are a hardcoded list from one run and must stay sorted
descending for the greedy least-loaded choice to balance well; a stale weight costs balance only.
