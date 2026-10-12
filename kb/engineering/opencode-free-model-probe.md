# OpenCode Free tier — model capability probe (2026-09-03)

Method: keyless POST to `opencode.ai/zen/v1/chat/completions` (empty `Authorization`,
system `User-Agent`). Model list is live from `/v1/models`; the `opencode-free`
provider profile is keyless by design (see `hermes_cli/.../opencode_free`).

## Availability (ping round, "say hi")
| Model | Verdict | Latency | Note |
|-------|---------|---------|------|
| laguna-s-2.1-free | OK | 2.7s | fastest, good structured answers; Hermes default_aux_model |
| ling-3.0-flash-fin-free | OK | ~3s | fast; but often returns content without answering the prompt format |
| nemotron-3.5-lightning-free | OK | 5-6s | emits full thinking preamble; verdict buried in reasoning |
| nemotron-3-ultra-free | OK | **41s** | slow on trivial request; verdict inside reasoning block |
| deepseek-v4-flash-free | DOWN | — | 400 "Model is unavailable" (upstream removed) |
| muse-spark-1.3-contributor-free | DOWN | — | 500 Internal server error |
| muse-spark-1.2-contributor-free | DOWN | — | 500 Internal server error |
| mimo-v2.5-free | RATE-LIMIT | — | 429 FreeUsageLimitError (quota) |

## Format-following on real PR #266 (TLS session-resume race test)
| Model | Verdict | #51 impact | Latency | Format |
|-------|---------|-----------|---------|--------|
| laguna-s-2.1-free | CORRECT | PARTIALLY-CLEARED | 4.6s | clean, all 4 lines |
| ling-3.0-flash-fin-free | — | — | 3.2s | no verdict (parrots prompt) |
| nemotron-3.5-lightning-free | (buried) | — | 4.9s | thinking preamble, no clean verdict |
| nemotron-3-ultra-free | (reasoning) | — | 41s | correct reasoning, slow |

## Conclusion
- Free tier is **unstable**: 3/8 down, 1 rate-limited at the moment of testing.
- **laguna-s-2.1-free** is the only one that both answers fast AND follows an exact
  4-line output format reliably. Good default for aux/derivative model.
- nemotron-3.5/3.0 are technically capable but emit long thinking blocks and are
  slow (3.0 extremely so) — poor for high-frequency review loops.
- Reasonable, fast code-review/issue-analysis proxy = **laguna** + (retry) **mimo**.
  For deep reasoning at lower cadence, a paid model is preferable; free tier is
  best for cheap auxiliary passes.

Caveats: all free models are "limited time" promo — expect churn. Free tier throttles
(free usage limit) so fan-out batches will hit 429. Track live list, don't hardcode.
