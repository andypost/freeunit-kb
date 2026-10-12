# Encoding contracts in FreeUnit

**Why the UTF-8 fixes keep needing follow-ups, and how to stop.**

Base: `origin/master` @ `279e1bb5` (#284 merged). PR #304 = `origin/fix/json-escape-invalid-utf8`.
All line numbers re-derived from those commits. Everything marked *ran it* was executed
against a real `unitd` (1.36.0, `build/sbin/unitd`) on 2026-09-09; everything else is a
code read and says so.

---

## 0. The call

1. **#304 diagnoses a real bug and fixes it in the wrong function.** Its escaping logic is
   provably correct — a brute force over every 1-, 2-, 3- and 4-byte input finds zero
   overflows and zero slack between the length pass and the print pass. But
   `nxt_conf_json_escape()` is not the access log's escaper. It is also the config API's
   printer, the state-file writer and the router config channel. Landing #304 as written
   silently rewrites operator config on disk (§3). **Rework, do not merge.**
2. **The reason this keeps happening is that FreeUnit has no encoding contract.** It has
   twenty-five byte boundaries and twenty-five ad-hoc answers (§2). Each fix lands at the
   sink that was reported. The next sink is still open, so the next report arrives.
   `share` got a NUL guard; `index`, twelve lines away, feeding the same `open()`, did
   not — and I served a file through it (§1.2).
3. **The module cannot express the operation these fixes need.** `nxt_utf8_decode()` never
   advances on failure, so "replace the bad byte and continue" — what every one of these
   fixes wants — is an infinite loop with this API. The only loop shape that terminates is
   "abort the whole string". That is why #304 had to hand-roll its own resync, and it is
   the root enabler of the treadmill (§4).
4. **One finding outranks the whole thread: a single request aborts a wasm worker** (§2.2,
   B0). Fix that first and separately.

The plan is §6. The mechanical gates that make this stick are §7.

---

## 1. The shape of the treadmill

### 1.1 The sequence so far

| | what it fixed | what it left open |
|---|---|---|
| #284 (merged) | object-format log injection: every member now goes through the real serializer | the serializer does no encoding repair |
| #304 (open) | the serializer's encoding repair | applies it to config too, which is not a log |
| not yet filed | string-format log injection (`$uri` is percent-decoded) | — |
| not yet filed | the config API emits non-JSON | — |

Each entry is the previous entry's blast radius. That is a treadmill, not a sequence of
unrelated bugs.

### 1.2 The purest example — `share` vs `index`

`src/nxt_http_static.c:459` rejects an embedded NUL in `ctx->share`, with a comment naming
`open()` as the sink. This is the fork's own hardening, and it is correct.

`conf->index` is `nxt_cpymem`'d into **the same buffer, feeding the same `open()`**, at
`src/nxt_http_static.c:520-522`. No guard.

*Ran it.* With `{"share": "<dir>$uri", "index": "a\u0000b"}` and a file named `a` in that
directory:

```
GET / HTTP/1.1  ->  HTTP/1.1 200 OK
                    Content-Length: 14
                    SERVED-FILE-A
```

The filename truncated at the NUL and served `a`. The fix went to the sink that was
reported. The sibling sink, in the same function, was not considered — because nothing in
the design says *where* NUL is supposed to be rejected.

### 1.3 The asymmetry that lets it in

*Ran it.* The config parser gives opposite verdicts to two spellings of the same thing:

| input | verdict |
|---|---|
| `"a\ud800b"` (escape form) | **400** — "This 6-byte sequence does not represent a valid UTF character" |
| `ED A0 80` (raw bytes, same code point) | accepted, stored, echoed back |
| `C0 AF` (overlong solidus) | accepted, stored, echoed back |
| `FF FE` (no valid sequence at all) | accepted, stored, echoed back |
| `"a\u0000b"` (escaped NUL) | **accepted**, stored as a real `0x00` |

The escape path is carefully validated (`src/nxt_conf.c:2098-2126`). The literal-byte path
is one line — `src/nxt_conf.c:1924`:

```c
if (nxt_fast_path(ch >= ' ')) {
    continue;
}
```

`ch` is a `u_char`, so every byte `0x80`-`0xFF` satisfies it, and when a string has no
escapes at all the second pass `memcpy`s it verbatim (`src/nxt_conf.c:2040-2042`).

**Validation exists for one spelling and not the other.** That is not a missing check; it
is a missing contract.

---

## 2. What a running FreeUnit does today

### 2.1 Confirmed by execution

**E1 — the config API emits bytes no JSON parser can read.** PUT a route header-match value
containing `FF FE`; unitd answers `Reconfiguration done.`, stores it, and returns it
verbatim from `GET /config` under `Content-Type: application/json`
(`src/nxt_controller.c:2815`). `json.loads()` on that response body raises
`UnicodeDecodeError: invalid start byte` at offset 144. RFC 8259 §11 gives
`application/json` no charset parameter — JSON text is UTF-8 — so this is a protocol
violation, not a cosmetic one.

**E2 — the on-disk state file holds the same bytes.** `state/conf.json` is not valid UTF-8
after that PUT. `nxt_controller_conf_store()` (`src/nxt_controller.c:2581-2593`) uses the
same printer.

**E3 — first-party tooling already assumes the contract the core does not enforce.**
`unitctl` parses the config response with `serde_json::from_reader`
(`tools/unitctl/unit-client-rs/src/unit_client.rs:284`), which requires UTF-8. The Python
suite does `json.loads` (`test/unit/control.py:27`). **A config `unitd` accepts and stores
cannot be read back by its own tools.**

**E4 — string-format access logs can be forged.** `$uri` is percent-decoded, so `%0A`
becomes a real newline:

```
format: "target=$request_line uri=$uri"
GET /x%0AInjected-Record HTTP/1.1
->  target=GET /x%0AInjected-Record HTTP/1.1 uri=/x
    Injected-Record
```

One unauthenticated request writes two records. `$request_line` is *not* decoded, so the
**default** format is unaffected — the exposure is configs using `$uri` or `$arg_*`.

**E5 — the request target carries arbitrary bytes.** `nxt_http_target_chars[256]`
(`src/nxt_http_parse.c:48`) initialises only its first 64 entries; `0x80`-`0xFF` fall
through with trap `0`. `GET /caf\xff\xfe HTTP/1.1` returns `200 OK` with the bytes intact
in `$uri` and `$request_line`.

**E6 — `index` truncates at NUL.** §1.2.

### 2.2 B0 — one request aborts a wasm worker

**High. Confirmed by code; not reproduced against a live wasm app (no wasm build here).**

`src/wasm-wasi-component/src/lib.rs:600`:

```rust
std::str::from_utf8(slice).unwrap()
```

Reached per request from `target()` `:494`, `server_name()` `:487`, and both halves of
every header field, `:511` and `:513`. The entry point is
`unsafe extern "C" fn request_handler` (`:175`), and **both** Cargo profiles set
`panic = 'abort'` (`src/wasm-wasi-component/Cargo.toml:33-37`). So it is `SIGABRT`, not a
caught `Result`, and it takes the worker process with every request in flight on it.

The input half is confirmed by execution (E5): `GET /\xff` reaches that `.unwrap()`, and
so does any header value with obs-text, which `src/nxt_http_parse.c:663-670` permits.
The module ships in `pkg/deb/Makefile.wasm`, `pkg/rpm/Makefile.wasm` and
`pkg/docker/Dockerfile.wasm`.

`git blame` puts line 600 in the fork-import commit, so this is inherited from upstream
nginx/unit, which is archived and will not fix it.

**The fix is one call**, and the correct pattern is already in this tree:
`src/otel/src/lib.rs:266` uses `String::from_utf8_lossy` with a comment explaining that
header values are arbitrary bytes. The wasi-http WIT interface models header values as
`list<u8>`, so nothing in the component interface objects.

### 2.3 The boundary inventory

Twenty-five sites where bytes of unknown encoding meet a consumer that assumes one. The
load-bearing rows:

| # | site | source | assumes | validated | consequence |
|---|---|---|---|---|---|
| 1 | `src/nxt_conf.c:1924` | POSTed config | JSON is UTF-8 | **no** | E1, E2 |
| 2 | `src/nxt_conf.c:2132` | `\uXXXX` escapes | valid scalar | surrogates yes, **NUL no** | §1.2 |
| 3 | `src/nxt_conf.c:2635` | every JSON string out | output is UTF-8 | **no** | E1 |
| 10 | `src/nxt_router_access_log.c:258` | `$uri`, `$arg_*` | text line | **nothing** | E4 |
| 11 | `src/nxt_http_parse.c:663` | header values | — | admits `0x7F`, `0x80`-`0xFF` | source for 19, 20 |
| 15 | `src/nxt_http_request.c:135` | `Host:` | hostname | `if (ch > ']') continue;` | any byte in `$host` |
| 18 | `src/nxt_unit.c:1928` | WS text frames | RFC 6455: UTF-8 | **none** | B4 |
| 19 | `src/java/nxt_jni.c:168` | header values, URI | JNI modified UTF-8 | **none** | B1 |
| 20 | `src/wasm-wasi-component/src/lib.rs:600` | target, headers | `&str` | `.unwrap()` | **B0** |
| 23 | `src/nxt_http_static.c:520` | config `index` | NUL-terminated | **none** | §1.2 |

**And the tree already contains the right answer, twice.** `src/otel/src/lib.rs:266` uses
`from_utf8_lossy`; njs substitutes U+FFFD in `njs_string_decode_utf8`. The visible
consequence: the same header logs as **raw bytes** through `$header_x` and as **U+FFFD**
through an njs expression. One header, two encodings, decided by which code path renders
it.

Every scripting module is deliberately byte-transparent and correct — Python WSGI
latin-1 (`src/python/nxt_python.h:21`), Ruby ASCII-8BIT, Perl with no `SvUTF8_on`
anywhere, PHP native byte strings, Node latin-1. **Only Java and the wasm component assume
UTF-8, and both are wrong.**

### 2.4 B4 — WebSocket

RFC 6455 §5.6 requires text-frame payloads to be valid UTF-8 and §7.1.5 the same of close
reasons; the mandated response is a close with status 1007. Unit validates nothing —
`NXT_WEBSOCKET_OP_TEXT` (`src/nxt_websocket_header.h:41`) is logged
(`src/nxt_unit.c:1928`) and never branched on.

The repository says so itself. `test/test_asgi_websockets.py:1102`:

```
#        Unit does not support UTF-8 validation
#
#        # 6_3_1 FAIL
```

over a disabled Autobahn case feeding `\xed\xa0\x80`. The failure instead surfaces inside
the app: `src/nxt_python_asgi_websocket.c:916` decodes strict and raises `RuntimeError`
(`:920-928`) rather than closing per protocol.

---

## 3. Why #304 is right about the bug and wrong about the location

The escaping logic is sound, and this is the one part of #304 that needs no further
argument. An independent reviewer built the branch and brute-forced every input of length
1-4 through verbatim copies of both passes, twice: once counting, and once under
`-fsanitize=address,undefined` with an **exactly-sized `malloc` buffer per case**, so a
single-byte overrun would have surfaced as an ASan heap-buffer-overflow report rather than
a counter. Both runs: **`overflows=0`, `slack=0`, max expansion `6/1`** (the sanitized run
took 25m30s and exited clean). Since the helper never looks past four bytes or `end`, that
is a complete proof for arbitrary length. There is no heap overflow, no undefined
behaviour, and the two passes agree byte for byte.

The problem is scope. `nxt_conf_json_escape()` (`src/nxt_conf.c:2635`) is reached from:

| caller | purpose | may bytes be rewritten? |
|---|---|---|
| `src/nxt_controller.c:2779` | `GET /config` response | **no** — the operator gets back what they PUT |
| `src/nxt_controller.c:2593` | `state/conf.json` | **no** — this is durable operator data |
| `src/nxt_router.c:1960` | app config to the worker | **no** — changes what the app receives |
| `src/nxt_router_access_log.c:340` | JSON log record | **yes** — this is the one #304 means |

Reproduced by the reviewer against the built branch:

```
origin/master:  {"root":"/srv/caf\xE9"}  ->  {"root":"/srv/caf\xE9"}
PR #304:        {"root":"/srv/caf\xE9"}  ->  {"root":"/srv/caf�"}
```

Non-UTF-8 filesystem paths are legal on Linux. A latin-1 `share` path or `environment`
value survives a `PUT`, is rewritten in `conf.json`, and after the next restart the router
opens a **different path**. Worse: object **keys** take the same escaper
(`src/nxt_conf.c:2502` and `:2553`), so a route header-match key would come back as a
different header name — a functional change, not a cosmetic one.

Two smaller points from the same review, both worth acting on:

- **6x amplification, newly reachable.** Emitting the six ASCII bytes of `�` per bad
  byte costs 6x on attacker-controlled obs-text, where the pre-PR reachable expansion for
  those bytes was 2x. Raw `EF BF BD` is 3 bytes and, after JSON decoding, indistinguishable
  from the escaped form — a genuine U+FFFD in the input is copied through raw anyway, so
  there is no disambiguation argument for the `\u` spelling.
- **The test's safety claim is false.** `src/test/nxt_conf_json_escape_test.c` says "under
  the sanitizers it is the ASan report that lands first". It is not: `nxt_mp_nget` with
  `size` ~20 against a 1024-byte-page pool takes the pooled small path, which has no
  redzone. `printed <= size` is the only net, and it is checked *after* the corruption.
  Since the passes provably agree exactly, assert `printed == size` plus a canary past
  `size` — equality also catches drift in the slack direction, which is the direction a
  refactor introduces silently.

---

## 4. The module cannot express what these fixes need

`src/nxt_utf8.c` is byte-identical to archived upstream. Its entire production surface is
two calls, both in `src/nxt_conf.c`:

- `nxt_utf8_encode` at `:2132` — emitting a `\uXXXX` escape during config parse.
- `nxt_utf8_length` at `:2711` — computing the **column number** for a parse-error message.

That second one is the only place in the whole product where UTF-8 validity changes
behaviour, and it is cosmetic. Dead in production: `nxt_utf8_decode2`, `nxt_utf8_casecmp`,
`nxt_utf8_lowcase`, `nxt_utf8_is_valid`, and `nxt_utf8_next`.

**4.1 The decoder accepts surrogates.** The final gate is `src/nxt_utf8.c:161`,
`overlong < u && u < 0x110000`. For lead `ED` the overlong floor is `0x07FF`, and
`0x7FF < 0xD800 < 0x110000`, so `ED A0 80` decodes to U+D800 and reports a 3-byte
sequence. Unicode 15 Table 3-7 restricts lead `ED` to trail `80..9F`. So
`nxt_utf8_is_valid()` — the function whose *name* promises the guarantee — blesses
WTF-8/CESU-8. It is harmless today only because it has no callers, and that is one new
caller away from evaporating.

**4.2 The API makes "skip and continue" an infinite loop.** Every error return leaves
`*start` untouched. So this hangs:

```c
while (p < end) {
    u = nxt_utf8_decode(&p, end);
    if (u == 0xFFFFFFFF) { continue; }   /* never advances */
}
```

There is no consumed-length and no error class, so a caller wanting "replace and continue"
must re-implement the lead-byte length rules itself. **Both production callers take the
only escape the API offers — abort the whole string — not because aborting is right for
them, but because it is the only shape that terminates.** #304 hand-rolls a one-byte
resync for exactly this reason. This is the root enabler: the API shape forces every
encoding fix to be local and bespoke.

**4.3 `nxt_utf8_next()` reads out of bounds.** `src/nxt_utf8.h:32-56` does
`do { c = *p; ... } while (p < end)` — it dereferences before the bounds test, so a buffer
ending in a lead byte overreads by one (ASan-confirmed on a 1-byte allocation holding
`0xC3`). It is dead, so it is a landmine rather than a wound — but it is precisely the
helper a future caller would reach for to resynchronise, and its stated contract already
disclaims the case where it matters.

**4.4 The test asserts the bug is a feature.** `src/test/nxt_utf8_test.c:98` is
`for (u = 0; u < 0x110000; u++)` with no surrogate skip, round-tripping encode then decode.
D800-DFFF pass. **Any conformance fix breaks this test by design of the test.**

**4.5 Dead weight.** `nxt_unicode_lowcase.h` (38,673 bytes) and
`nxt_unicode_macosx_lowcase.h` (24,356 bytes) are generated from **CaseFolding-6.3.0.txt**
— Unicode 6.3.0, September 2013, twelve major releases stale. `src/nxt_utf8.c` is in
`NXT_LIB_SRCS` (`auto/sources:33`), so `size -A build/src/nxt_utf8.o` gives
`.rodata 12992` + `.data.rel.ro.local 4168` = **~17.2 KB of table data in every `unitd`**,
indexed by nothing. Their regenerator, `utf8_file_name_test`, is built by CI
(`auto/make:262`, `.github/workflows/build-test.yml:590`) and **never executed**.

**4.6 No fuzz gate.** `.github/workflows/fuzzing.yml:5-24` gates on `src/nxt_http*`,
`src/nxt_h1proto*`, `src/nxt_conf*`, `src/nxt_controller*`. **Editing `src/nxt_utf8.c`
runs no fuzzer.** And `nxt_utf8_fuzz` (`fuzzing/nxt_basic_fuzz.c:186-197`) calls
`nxt_utf8_decode` exactly **once**, not in a loop, so it cannot find a multi-character
state bug.

---

## 5. The design: three contracts, declared per boundary

Every boundary in §2.3 gets exactly one label. The labels are not new mechanisms; they are
a decision about *where* the check lives, which is the thing currently missing.

**Contract A — opaque bytes.** The consumer must not assume an encoding, and lengths travel
with the data. HTTP bodies, header values handed to applications, every scripting module.
*Already correct everywhere except Java (B1) and wasm (B0).* Enforcement: no encoding code
at all, and no `strlen` on framed data.

**Contract B — UTF-8, enforced by rejection at ingress.** The producer is the operator, who
can be told "no". Config JSON, on both the control API and the state file.
Enforcement: **the parser**. One check, at `src/nxt_conf.c:1924`.

**Contract C — UTF-8, enforced by substitution at ingress.** The producer is an anonymous
client who cannot be told "no" — you do not reject a request because its User-Agent has a
stray byte. Access-log values, and anything else request-derived that must be rendered
into a structured format. Enforcement: **substitute U+FFFD as the value enters the
structure**, never at the printer.

From which follows the invariant that makes the printer trivially correct:

> **Every string inside an `nxt_conf_value_t` is valid UTF-8.**

Contract B establishes it for config by rejecting. Contract C establishes it for log
records by substituting. Given the invariant, `nxt_conf_json_escape()` needs **no encoding
logic whatsoever** — its job is quoting, and quoting only. That is why #304 belongs in a
different function: it is repairing data at the point where the invariant should already
hold, instead of at the point where it is established.

This also settles the question the earlier plan doc left open ("pick one: `\uXXXX` or
U+FFFD, but state it"). The answer is **both, at different boundaries**: reject where you
can, substitute where you cannot, and never repair at the sink.

---

## 6. The plan

Ordered by severity times independence. P0 and P1 are independent of everything else.

### P0 — `wasm-wasi-component`: stop aborting on obs-text
`from_utf8` to `from_utf8_lossy` in `get_str` (`src/wasm-wasi-component/src/lib.rs:592-600`),
matching `src/otel/src/lib.rs:266`. Return `String`/`Cow<str>` instead of `&str`.
Test: a request with `\xff` in the target and in a header value against a wasm app.
Small, urgent, backportable to `1.34`. **File the issue first** — this is a remote
unauthenticated worker abort and may warrant an advisory. Upstream is archived and affected.

### P1 — `nxt_utf8`: make the API able to express repair
No product behaviour change (every function touched is dead in production except the
surrogate gate, which has no production caller).
- Reject surrogates at `src/nxt_utf8.c:161`, so `nxt_utf8_is_valid()` means what it says.
- Give the decoder a resync: either advance `*start` past the **maximal subpart**
  (Unicode 15 §3.9, D93b) on failure, or add an out-parameter for bytes consumed. Without
  this, every future repair site re-implements the byte-length rules, as #304 did.
- Delete `nxt_utf8_next()` — dead and out-of-bounds (§4.3).
- Delete `nxt_utf8_casecmp`, `nxt_utf8_lowcase`, both `nxt_unicode_*lowcase.h`, the
  generator and `utf8_file_name_test`: ~17.2 KB of Unicode 6.3.0 data in every binary,
  reachable from nothing, regenerable from git if ever wanted.
- Fix `src/test/nxt_utf8_test.c:98` to skip D800-DFFF and assert they are *rejected*.
- Add `src/nxt_utf8*` to `fuzzing.yml` paths, and make `nxt_utf8_fuzz` loop over the input.

### P2 — replaces #304: `nxt_utf8_sanitize()`, applied at the log sink
`nxt_int_t nxt_utf8_sanitize(nxt_mp_t *mp, nxt_str_t *dst, const nxt_str_t *src)` — scans,
and only allocates when the input is actually invalid (clean strings alias, no copy).
Uses P1's resync. Emits raw `EF BF BD` with maximal-subpart substitution: 3x worst case
instead of 6x, one U+FFFD per bad sequence instead of per byte, and it matches what njs
and otel already do in this tree.
Called from `nxt_router_access_log_json()` (`src/nxt_router_access_log.c:328`), on the
`str` returned by `nxt_tstr_query()`, **before** `nxt_conf_set_member_string()`.
`nxt_conf_json_escape()` is left untouched — **zero config blast radius**.
Keep #304's test, retargeted at the sanitizer: assert `printed == size` plus a canary past
`size` (§3), and add the five cases the reviewer listed — `E0 80 AF`, `C1 BF`, `E2 82 7A`,
`F4 90 80 80`, and a *valid* multi-byte sequence butting against `end`.

### P3 — config ingress validation (Contract B)
- Validate literal-byte runs as UTF-8 in `nxt_conf_json_parse_string()`
  (`src/nxt_conf.c:1924`), with a parse error in the style of the existing `\uXXXX` ones,
  naming the offset. Closes E1, E2 and §1.3.
- Reject `\u0000` at `src/nxt_conf.c:2132`. An embedded NUL has no legitimate use in any
  config string and is a path-truncation primitive (§1.2).
- **State-file load must sanitize and warn, not reject** — a stored `conf.json` containing
  these bytes predates the check, and refusing it would brick an upgrade. Reject on the
  control API; repair on the way in from disk, once, loudly.
- Needs a CHANGES entry: this is a compatibility change.

### P4 — the `index` NUL guard
P3 makes it unreachable, but add the `memchr` guard beside its sibling at
`src/nxt_http_static.c:459` anyway. Cheap, and defence in depth is already the house
position at that exact spot.

### P5 — Java: `NewStringUTF` on raw request bytes (B1)
`src/java/nxt_jni.c:168` requires *modified* UTF-8 and is undefined on invalid input. Two
consequences: obs-text corrupts the `String`, and **any astral-plane character — an emoji
in a URI — is mis-decoded**, because modified UTF-8 wants CESU-8 surrogate pairs, not
4-byte sequences. Fix: `NewString` from an explicitly decoded `jcharArray`. Header *names*
are safe (the parser restricts them to tchar).

### P6 — string-format access log escaping
The remaining CWE-117 hole (E4). Needs an `"escape": "default" | "none"` option, nginx's
convention, defaulting to `default`. Behaviour change for every existing deployment,
so: own PR, own CHANGES entry, and the advisory for #284 must say the string format
remains affected until this lands.

### P7 — WebSocket UTF-8 validation (B4)
RFC 6455 §5.6 / §7.1.5, close status 1007. Largest of these and the least urgent. The
payoff is concrete: re-enable the disabled Autobahn cases at
`test/test_asgi_websockets.py:1102` and `:1250` instead of shipping a comment that says
we do not conform.

**Dependencies:** P2 needs P1. P4 is subsumed by P3 but harmless alongside. P0, P5, P6, P7
are independent of everything.
**Backportable to `1.34` cleanly:** P0, P1, P2, P4.

---

## 7. The gates that stop the next one

A plan that relies on remembering this is worth nothing. Each of these is a check that
fails loudly:

1. **A round-trip fuzz target.** `nxt_conf_json_parse` then `nxt_conf_json_print`, then
   assert the output is valid UTF-8 and re-parses to the same value. This is the single
   highest-value addition: it catches E1, E2, the surrogate asymmetry, and any future
   printer change, without anyone having to think of the case. `src/nxt_conf*` is already
   in the fuzz gate.
2. **`src/nxt_utf8*` and `src/wasm*` added to `fuzzing.yml` paths** (§4.6).
3. **A pytest that PUTs each malformed spelling** — raw `FF`, `ED A0 80`, `C0 AF`,
   `\u0000` — and asserts `400` with a position, after P3. Four assertions, permanently.
4. **An assertion in the test harness, not in a test.** `test/unit/control.py:27` already
   does `json.loads`; make the config response decode explicitly and fail with a clear
   message. Then *every* test in the suite is a regression test for E1.
5. **A grep gate for `strlen` on framed data** in the module glue — B6
   (`src/wasm/nxt_wasm.c:235-244` recomputes `strlen` instead of using the
   `r->*_length` it was handed). Not exploitable today, because it rests on a parser
   invariant rather than on its own framing. That is the same bet this whole document is
   about.

---

## 8. What to do with #304 right now

Its author found a real bug, wrote a genuine regression test that fails on `master` and
passes on the branch, and got the hard part — the two-pass byte accounting — provably
right. None of that is wasted: it becomes P2 nearly unchanged.

What has to change is the function it lands in. Post the finding (§3) with the
`caf\xE9` reproduction and the object-key consequence, and ask for it to move to a
sanitizer called at `src/nxt_router_access_log.c:328`, with raw `EF BF BD` and
maximal-subpart resync. The escaper stays as it is: quoting is its job, and after P3
nothing else is needed there.

Style points a maintainer will raise anyway: `nxt_length("\\uFFFD") - 1` at
`src/nxt_conf.c:2656` and `sizeof("\\u001F") - 2` at `:2683` compute the same thing two
ways in one function; the copyright header says `NGINX, Inc.` where every test this fork
has added says `F5, Inc.`; and `auto/sources` inserts the new test in the port block
rather than beside `nxt_conf_parse_test.c`.

---

## Appendix — reproduction

All of §2.1 came from one `unitd` on a scratch control socket:

```sh
build/sbin/unitd --no-daemon --control unix:/tmp/uc.sock \
    --pid $S/unit.pid --log $S/unit.log --statedir $S/state --tmpdir $S/tmp

# E1/E2 - invalid UTF-8 round-trips through config and state
printf '{"listeners":{"127.0.0.1:8099":{"pass":"routes"}},"routes":[{"match":
  {"headers":{"X-T":"caf\xff\xfe-bad"}},"action":{"return":200}}]}' > cfg.json
curl -s --unix-socket /tmp/uc.sock -X PUT --data-binary @cfg.json http://localhost/config/
curl -s --unix-socket /tmp/uc.sock http://localhost/config/ | python3 -c \
  "import json,sys; json.loads(sys.stdin.buffer.read())"   # UnicodeDecodeError
xxd $S/state/conf.json | grep 'caf'

# E5 - raw high bytes in the target
printf 'GET /caf\xff\xfe HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' \
  | nc 127.0.0.1 8099 | head -1                            # HTTP/1.1 200 OK

# E6 - index truncates at NUL
mkdir -p share && echo "SERVED-FILE-A" > share/a
# config: {"share": "$PWD/share$uri", "index": "a\u0000b"}
curl -s -i http://127.0.0.1:8099/ | head -1                # 200, body "SERVED-FILE-A"
```

The socket path must be short — `sun_path` is 108 bytes and a scratchpad path overflows it.
