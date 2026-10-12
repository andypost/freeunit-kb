# zen-quorum: PR #320 — wasm: stop the rest of the request path from aborting the worker

_gathered 2026-09-12 · keyless OpenCode Free tier · 3 verdicts, 1 model quota-blocked_

**PR:** freeunitorg/freeunit#320 · branch `fix/wasm-worker-abort-followup` · head `168040a4`
base = master `62e10c59` (later rebased-free against `99086536`) · 2 files, +211/−64

**Body:** (see PR) Two commits on the wasm request path: a negative `nxt_unit_request_read()`
wrapped into `usize` moved `set_len()` past the allocation; and the remaining libunit response
calls / guest trap / dropped sender all aborted the worker under `panic = 'abort'`.

## Run 1 (blind — prompt truncated, DISCARD)

2× PARTIAL, 1× CORRECT → DIVERGENT. Both PARTIAL votes said "the diff does not show the
`request_read` fix". That was true of the PROMPT, not of the PR: the runner fetched
`diff[:4000]`, printed `diff[:3000]`, and attached full source only for `.c`/`.h` — a Rust PR
got no code context. `verify_spots()` then called the Rust symbols `MADE-UP?` because its
symbol index only recognises C tokens. Artifact, not dissent.

## Run 2 (after fixing the prompt context: caps 20000/19000, `CODE_EXTS` +.rs/.py)

| model | verdict | SPOT |
|---|---|---|
| muse-spark-1.3-contributor-free | PARTIAL | `send_response` keeps `headers().len().try_into().unwrap()` and the header-size sum `.try_into().unwrap()` |
| muse-spark-1.2-contributor-free | PARTIAL | same two unwraps + `request_handler`'s `blocking_send(...).unwrap()`; also claimed the diff still truncates (it no longer does) |
| ling-3.0-flash-fin-free | CORRECT | none |
| mimo-v2.5-free | FAIL 429 | `FreeUsageLimitError` (shared quota) — did not vote |

Window 3/4. Divergence on the enum, agreement on the substance: both PARTIALs name the same
residual class, and neither disputes the two named fixes.

## Ground-truth of the SPOTs (checked against branch code, not the claim)

- `try_into().unwrap()` in `send_response`: **unreachable in practice.** `headers().len()`
  (usize→u32) needs >4 billion headers, and the size sum needs >4 GiB of header bytes in one
  response. Theoretical residue, not a trigger. Distinct from the u8 header-NAME conversion
  (reachable at 255 bytes), which this PR does fix via `bail!`.
- `blocking_send(...).unwrap()` / `GLOBAL_STATE.get().unwrap()` in `request_handler`:
  **real but shutdown-only** (the channel closes when the runtime goes away). Pre-existing,
  untouched by this PR.
- Both fixes as described are present and correct in the branch code: negative read → error,
  zero read → break, size argument = real remaining space, plus a guard rejecting a count
  larger than the space given; `handle()` wrapper + `check_rc()` + `GuestTask` (Drop aborts an
  un-joined handle, `join()` takes it out first); `response_started` set only after
  `response_send` — verified against libunit, where a second `response_init` before the status
  line is a documented duplicate-init path, not an abort.
- muse-1.2's "obs_text expects 200 while the body claims 400" is a misreading: the 400s are the
  two requests in `test_wasm_component_unrepresentable_request` (obs-text in `Host`, `<` in the
  target); `test_wasm_component_obs_text` expects 200 for obs-text in the target/header value.
  Body wording ("two regression tests") is loose for "two cases of one test".

## Verdict

APPROVE, non-blocking notes only. Not client-drivable; the guest-reachable abort (>255-byte
response header name) is fixed. Two follow-ups worth a line each if the file is to have zero
request-path `unwrap()`s, plus the doc-comment drift (`GuestTask` still asserts the
client-disconnect trigger that #318's own correction retracts). #318/#319 do not auto-close
("closing #NNN" is not a GitHub keyword).
