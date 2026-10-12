# zen-quorum: FreeUnit capget-blokkature decision (2026-09-03)

_gathered keyless OpenCode Free tier · task = choose among real options on the capget chain_

## Context (ground truth from `capget-fallback-plan.md`)
Fact: `unitd` exited when `capget()` was filtered by seccomp (EPERM/ENOSYS).
PR #254 = warn+continue on ONLY those two errnos (narrow set),
fail-closed on EINVAL/EFAULT (a real Unit bug, not an operator policy).

## Options actually considered
| id | option | stance |
|----|--------|--------|
| A | PR #254 warn+continue on EPERM/ENOSYS (narrow) | in this PR |
| B | unconditional "unknown→none" | rejected (silent downgrade when setid==0) |
| C | drop caps in app-child after fork (`capset(0)`+`PR_CAP_AMBIENT_CLEAR_ALL`) | deferred to separate plan §4.5 |
| D | `capset(0)` on fallback in main | rejected (strips CAP_NET_BIND_SERVICE before bind → :80 dead) |

## Opinions captured (3-model window)
| model | latency | verdict | why |
|-------|---------|---------|-----|
| laguna-s-2.1-free | 4.4s | CORRECT | — (answer out of requested A/B/C/D schema — parse gap) |
| ling-3.0-flash-fin-free | 26.0s | PARTIAL | "recommended approach (A, warn+continue) continues execution with potentially reduced capabilities, which could mask security issues." |
| nemotron-3.5-lightning-free | 50.3s | (none) | thinking-preamble truncation; no verdict in window |

## Divergence
Consensus 1/2 on majority (CORRECT/positive vs PARTIAL/neutral) — **DIVERGENT**,
report as open question. Do not let one fast model (laguna) outvote the cautious
one (ling). Note: the parse only captured the CORRECT/PARTIAL/WRONG schema, NOT the
requested A/B/C/D — the runner cannot yet record a freeform verdict value.

## Parse gap found (action item)
`zen_quorum.py` pins verdict to `CORRECT|PARTIAL|WRONG`; a prompt that asks a
multi-choice (A/B/C/D) is mis-parsed and the real choice is dropped. Fix: accept a
freeform `VERDICT: <value>` (not an enum) so the runner can record A/B/C/D/COMBO.
Only then will a decision-quorum be trustworthy.
