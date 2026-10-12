# FreeUnit OTel — Perf Regression (#221) Resolution Log

**Created:** 2026-08-28
**Status:** #221 CLOSED (COMPLETED) — fixes 1-6 shipped, fix 7 explicitly deferred
**Related:** PR #218/#220 (lifecycle), #225 + #226 (perf fixes)

---

## The problem (issue #221)

Enabling OpenTelemetry ~doubles router CPU per request; ~half avoidable
synchronous work. Measured (Run 2, thread-attributed, 8 interleaved cycles):

| | router thread (sync) | export threads | process total |
|---|---|---|---|
| telemetry off | 55.2 µs | — | 55.2 µs |
| otel, ratio 1.0 | 86.0 | 29.9 | 115.9 (+106%) |
| otel, ratio 0.1 | 78.3 | 2.4 | 80.7 (+47%) |

**+27.5 µs synchronous delta** is ~4.5 sd above noise floor. ~47% of added cost
is genuinely synchronous. ~13 C→Rust FFI crossings + ~25-30 heap allocs per
traced request.

**Why sampling didn't help before:** `nxt_otel_rs_add_attr/build_span` ran
before `is_recording` was consulted — all sprintf/pool/propagation ran
unconditionally. Turning sampling down bought back the exporter but left the
request-path tax.

## Fixes 1-3 (PR #225, MERGED e21bc5bc)

1. **is_recording gate** — one call after span creation; skip HEADER/BODY/
   COLLECT work when false, keep propagation (W3C requires traceparent reach
   peer). **The only measured win**: −54% request-path cost at ratio 0.1.
   No effect at ratio 1.0 (by construction).
2. **Cache tracer at init** — `RwLock<Option<BoxedTracer>>` beside provider;
   removes an RwLock + provider clone + Box per request.
3. **Delete "Unit Attribute" event** — duplicated span context; also a bug fix
   (was added twice on errored requests via propagate_header + error_path).

## Fixes 4-6 (PR #226, MERGED defd7e26)

4. **Static attribute keys** — 11 keys → `static [Key; NXT_OTEL_ATTR_MAX]` of
   `Key::from_static_str`, indexed by `nxt_otel_attr_id_t`; mismatched count =
   compile error.
5. **Integer attributes as i64** — status_code / body.size → `Value::I64`;
   deletes snprintf round-trips + math.h.
6. **One FFI crossing per stage** — `nxt_otel_rs_add_attrs()` stack-built array;
   request stage 8→1 crossings, status 3→1. Deliberately did NOT use
   `SpanBuilder::with_attributes` (would build before sampling decision,
   undoing fix 1).

## Measured (from #225 + #226)

| | otel tax @ ratio 1.0 | @ ratio 0.1 |
|---|---|---|
| before | 18.55 µs | 15.45 µs |
| after | 18.52 µs | **7.10 µs** |

Honest accounting: at ratio 1.0 the tracer-cache + event-delete are
**measured free** (−0.55 ± 2.28 µs), not wins. Only the gate earns a number.
`sampling_ratio` now means what an operator expects (was −17%, now −62%).

## Fix 7 — DEFERRED, NOT DONE ❌

> "Move span construction off the router thread entirely, or link a
> thread-caching allocator into the staticlib to defuse the cross-thread
> free contention. Measure after 1-6 before considering either."

Author's note: "Only if the profile still demands it."

**What remains at `sampling_ratio: 1.0`:** roughly **+27.5 µs synchronous**
per request (the gate does nothing at ratio 1.0 by construction). Fix 7 is the
only path to remove that — either:
- (a) move span construction off router thread (large: lifetime/GC work), or
- (b) thread-caching allocator in staticlib (fixes cross-thread free
  contention, not the span-build itself).

**Assessment:** in production `ratio 1.0` is rare (most run 0.1-0.01, where
the gate saves 54%). Fix 7 is not a release blocker. Track it as a known
remainder, not a lost item.

## Status

| Fix | PR | Status |
|-----|-----|--------|
| 1-3 (gate, tracer, event) | #225 | ✅ MERGED |
| 4-6 (keys, i64, one-crossing) | #226 | ✅ MERGED |
| 7 (off-thread span / allocator) | — | ❌ DEFERRED (measure after 1-6) |

#221 → CLOSED (COMPLETED). Fix 7 remains as a documented follow-up.
