# CI pipeline balance — FreeUnit "Build & Test (Linux)"

Measured 2026-09-15 over the last 10 completed runs of the workflow (per-leg medians,
`jobs` API: duration = completed−started, wait = started−run created). Post-#395/#396 state.

## Per-leg medians (seconds)

| leg | dur | wait |
|---|---|---|
| python-3.12 | 378 | 183 |
| python-3.13 | 363 | 188 |
| wasm-wasi-component | 330 | 180 |
| java-26 / 25 / 21 / 17 | 293 / 288 / 287 / 275 | 206 / 217 / 206 / 122 |
| python-3.14 | 290 | 221 |
| unit | 281 | 232 |
| go-1.25 / 1.26 | 226 / 220 | 281 / 152 |
| node-20/26/22/24 | 196 / 194 / 188 / 182 | 229 / 233 / 251 / 202 |
| ruby-3.3/3.4/4.0 | 177 / 167 / 164 | 186 / 196 / 196 |
| perl / php-8.4 / php-8.5 / php-8.3 | 165 / 164 / 164 / 156 | 100 / 267 / 204 / 167 |
| wasm | 73 | 92 |
| compression-range-tests | 50 | 62 |
| openssl4 / c-tests / prepare | 39 / 38 / 5 | 61 / 66 / 70 |

Sum of per-leg medians: **5353s = 89 min** of runner time per run. 26-27 legs.

## Where the time goes

Step-level (job 35003199963): every matrix leg pays the same fixed cost —
`Configure unit` ~6s + `Make unit` 43-49s + caches/checkout/installs ~35-45s ≈ **85-100s**,
then runs only its own module + pytest (python 287s, unit 196s, java 209s, node 114s).
All 26 matrix legs share ONE `Configure unit` definition (same flags), so that build is
identical across legs and is the same work repeated 26 times: **~37-43 min of the 89**.

Test-level wins already landed (same day): `Connection: close` default (unit leg −259s vs
270s predicted from the 9 affected one-shot sites), python-leg sharding (#396, −7.8..−9.0 min
per leg), `test_asgi_websockets_large` 30.21s → 0.22s (measured, lands with #398).

## Span is scheduling-bound, not work-bound

Observed run spans (max(completed)−min(started)): 512-910s; longest leg 380s;
max simultaneous jobs inside one run: 11-25 (varies — the concurrency budget is repo-wide and
shared with the other PR runs in flight). So 130-530s of each span is queue wait, and the
per-leg medians wait 60-281s before starting.

Floor: with a dedicated 20-slot budget, sum/slots = 268s, longest leg = 378s → makespan
≈ longest leg ≈ 6.3 min. Today's 8.5-15 min is contention, not test design.

## Levers, ranked by measured payoff

1. **Build the core once, hand it to the legs as an artifact.** All legs configure the core
   identically, so one `build` job (or `prepare`) can upload `build/`; legs then only
   `configure <module>` + `make <module>`. Saves ~45-55s × 25 ≈ **−19 min/run** and shortens
   every short leg (node 214→~160s).
2. **Fold same-work runtime versions into one job** (node 4→2, ruby 3→2, php 3→2). The win is
   not test time but the repeated ~90s fixed cost plus one less scheduling slot; 6 fewer legs
   ≈ −9 min/run. Do NOT fold java (two versions in one job → ~500s critical path, worse than
   today's 380s longest) or python (the three versions carry the sharded shared suite, #396).
3. **Consolidate the tail:** c-tests (38s) + openssl4 (39s) + wasm (73s) as one job = one slot
   for ~150s instead of three slots — marginal, but frees two slots.
4. **Fairness between concurrent runs:** per-matrix `max-parallel` makes the queue move evenly
   instead of one run taking the whole budget; it does not speed a single run. Only worth it if
   the queue, not the run, is the pain.
5. **Coverage is not the knob.** The version matrices are the point; the duplication that was
   removable (shared suite × 3 python legs) is already gone via sharding.
