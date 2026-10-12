# zen-quality: full-toolset vs limited-toolset review comparison (2026-09-03)

_Goal: measure how much review quality degrades when the agent (SOUL) is stripped
of terminal/gh/web/search and LEFT WITH read_file (local KB) only. This is the
"internal variant" quality gate — what can the coordinator actually deliver on
trusted local context alone, vs with live repo access._

Task under test: FreeUnit PR #254 "capability: keep running when capget() is filtered".

## Metric

| axis | full-toolset | limited (file only) |
|------|--------------|---------------------|
| can fetch PR diff | yes | NO |
| can read source in repo | yes | NO (only KB) |
| can verify a SPOT symbol | yes (rg + symbol index) | NO |
| can check CI/state | yes (gh) | NO |
| verdict grounded in CODE | yes | only in KB prose |
| risk of misled by stale doc | low | HIGH |
| honesty about limits | — | must state them |

## Full-toolset baseline (this run, models on real diff)

- laguna-s-2.1-free: PARTIAL · NOT-CLEARED · RISK=medium
  - WHY: "correctly handles capget() filtering with a narrow errno check and
    preserves the warning pre-daemonization, but diff truncated at 'Residual'
    and omits src/nxt_capability.c/h changes"
  - SPOT: "CHANGES describes app processes no longer inheriting unitd's
    capabilities (clearing permitted/effective/inheritable/ambient after fork),
    but none of the shown diffs for nxt_capability.c / nxt_process.c /
    nxt_runtime.c include the capability-reduction logic" — a REAL potentially
    missing implementation or missing diff. Verifiable, concrete.
- ling-3.0-flash-fin-free: (verdict missing this pass — retry) · PARTIALLY-CLEARED · RISK=medium

## Notes / bugs found this pass
- laguna SPOT field OVER-CAPTURED: bled `CONCLUSION=NOT-CLEARED RISK=medium`
  into SPOT value (parser didn't clamp SPOT to its own token). Fix: clamp SPOT
  the same way as VERDICT (split on \n/:: before storing).

## Limited-toolset result
_Appended automatically when cron job 6cc7f3f97b7a fires (file-only, no terminal,
no gh, no web). Compare: can it VERIFY the capability-clearing SPOT? Can it even
state the diff is missing? Does it over-claim from KB prose alone?_

**Job 6cc7f3f97b7a REMOVED 2026-09-10** (admin cleanup; was disabled). Kept as a
record of the limited-toolset experiment; output preserved at
`/opt/data/cron/output/6cc7f3f97b7a.retired-20260910/`. Do not re-create unless
re-running the experiment.
