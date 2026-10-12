# OpenCode Free tier — model tracking (SOUL ops reference)

_2026-09-03. Ground truth for the keyless OpenCode Free relay and the zen-quorum
infrastructure. This is the canonical reference; the short fact lives in the
`zen-quorum` skill and in MEMORY as a one-line pointer only._

## Why keyless

The `opencode-free` provider profile is **keyless by design**: it sends an EMPTY
`Authorization` header (`_KEYLESS_HEADERS` in `opencode-free/__init__.py`). The
relay serves free-tier models anonymously and 401s any unrecognized bearer — so
holding a key is pointless and sending a placeholder would break it. It also
sends `HTTP-Referer` / `X-Title` / `User-Agent` attribution headers.

## Live catalog

```bash
curl https://opencode.ai/zen/v1/models        # full list (66 models 2026-09-03)
```

## Free-tier status — 2026-09-04 (live probe)

| Model | Status | Latency | Note for quorum |
|-------|--------|---------|-----------------|
| laguna-s-2.1-free | REMOVED | 401 both wires | **gone from live catalog** 2026-09-06 — do not plan around it |
| ling-3.0-flash-fin-free | ALIVE via chat | ~1.1s | fast, but UNRELIABLE (flips 503; was reliable 09.03) |
| nemotron-3.5-lightning-free | ALIVE via chat | ~0.8s | fast today; format-ignorant (template echo) |
| nemotron-3-ultra-free | ALIVE via chat | ~1.6s | **back** — was 41s/timeout on 09.03–09.06; recheck speed before quorum |
| deepseek-v4-flash-free | DOWN | 400 | still down (upstream removed) |
| muse-spark-1.3/1.2-contributor-free | ALIVE via responses | ~1.0s | **codex_responses wire** — 500 on chat/completions is a wrong-endpoint artifact, not downtime |
| mimo-v2.5-free | RATE-LIMIT | 429 | quota-limit (appeared since 09.03) |

**Change vs 09.03:** laguna REMOVED from catalog (401 both wires); nemotron-3-ultra
BACK (~1.6s, was 41s/timeout); nemotron-3.5 fast again (~0.8s); mimo-v2.5 429.
Wire rule: muse-spark pair ONLY on responses; ling/nemotron/deepseek/mimo ONLY
on chat. Quorum today: muse 1.3/1.2 + ling + nemotron-3.5/ultra are all alive —
but the runner only speaks chat, so muse votes need the responses wire first.

## 2026-09-06 — laguna REMOVED from catalog

**`laguna-s-2.1-free` is GONE from `GET /v1/models`** — the live catalog now lists
7 free models, without laguna. It was the format-anchor (~100% structured verdicts,
avg 1.8s) on 09-03; today it is absent entirely, not merely down.
- This explains laguna "DOWN" in the profile: it was not a transient flip, it
  was **removed** by the relay.
- **New model appeared:** `deepseek-v4-flash-vision-exp` (owned_by=opencode) —
  this is the current session model (DeepSeek V4, vision).
- The rest of the catalog delta (claude-fable-5, claude-opus-5, gemini-3.x,
  gpt-5.x, kimi-k3, qwen3.6-plus) are **paid**, not free-tier.
- **Quorum implication (updated):** muse-spark 1.3/1.2 are alive (~1s, responses
  wire) and nemotron-3-ultra is back (~1.6s, chat) — so votes exist again, but
  the runner only speaks chat. Until it learns per-model api_mode, muse votes
  stay out of reach; usable chat quorum today = ling + nemotron-3.5/ultra.


Free tier = models id-suffixed `-free`. On 2026-09-03 there were 8:
`laguna-s-2.1-free`, `ling-3.0-flash-fin-free`, `nemotron-3.5-lightning-free`,
`nemotron-3-ultra-free`, `mimo-v2.5-free`, `deepseek-v4-flash-free`,
`muse-spark-1.3-contributor-free`, `muse-spark-1.2-contributor-free`.

**The list rotates** — free models are "limited time" promo. Never hardcode; read
the live catalog, and treat a DOWN model as "unavailable now", not "wrong".

## Per-model limits (from `opencode-zen/__init__.py` + `agent/reasoning_effort.py`)

reasoning_effort value-sets are the ONLY accepted values — anything else 400s:

| Model family | reasoning_effort | max_tokens | api_mode |
|---|---|---|---|
| Ox Alpha (`x-preview-f-free`) | `low, high, max` | — | chat_completions |
| GLM 5.2 | `high, max` | — | chat_completions |
| Kimi K2 | `low, medium, high` | — | chat_completions |
| DeepSeek V4 thinking | `low, medium, high, max` | — | chat_completions |
| mimo-v2.5-pro | — | **131072** (>400s) | chat_completions |
| muse-spark (`muse-spark-*`, incl. `-contributor-free`) | — | — | **codex_responses** (`/v1/responses`; chat/completions 500s — wrong wire) |
| keyless free tier | **not forwarded** (server default) | — | chat_completions |

**Key:** for the keyless free tier the provider does NOT forward `reasoning_effort`
— models think as long as the server decides. Do not try to tune effort on a `-free`
model; it is ignored. Control "how much thinking" only by picking the model.

## Profile accumulator (every-6h cron `6c821eeaa568`)

`tools/zen_models_profile.py` runs every 6h (wrapper `scripts/zen-models-profile.sh`,
`script = filename only`). It ACCUMULATES per-model knowledge into
`~/.hermes/zen-models-state.json`:

- `models.<id>.history` — up to 200 samples (6h cadence) `{ts, alive, dt, slow, err}`
- `models.<id>.latency` — rolling `{n, min, max, avg, p95}`
- `models.<id>.skills` — specialization counters (tagged via `--skill/--task`)
- `models.<id>.last` — most recent snapshot
- `model_specs.<id>` — the static limit table above (re-read from source only rarely)

Probe is cost-bounded: `max_tokens=4`, 20s timeout per model, so even deep
thinkers are gated. Output = only the delta (UP/DOWN/speed-flip); silent when
nothing changed (watchdog pattern).

Commands:
```bash
python3 tools/zen_models_profile.py --report                 # readable summary
python3 tools/zen_models_profile.py --force                  # refresh now
python3 tools/zen_models_profile.py --skill <model> --task <type>   # tag specialization
```

## Quorum runner

`tools/zen_quorum.py` — independent verdicts from several models on one issue/PR:
```bash
python3 tools/zen_quorum.py --repo freeunitorg/freeunit --pr 254
python3 tools/zen_quorum.py --text "<problem>" --choices "A|B|C|D"   # freeform pick
python3 tools/zen_quorum.py --pr 254 --save-kb
```
- Accepts compact `VERDICT: A :: WHY: ...` and per-line formats; clamps verdict to
  first token.
- Parses verdict from `content`, `reasoning_content`, `reasoning`; retries 429/503/500.
- `max_tokens=4000` default (thinking preamble eats it; a low cap truncates BEFORE
  the verdict and returns a prompt fragment).
- Reports per-model verdict + divergence block; `DIVERGENT` = open question, don't
  let one fast model outvote a slow careful one.

## Measured model behaviour (2026-09-03)

| Model | alive | latency | skills | verdict |
|---|---|---|---|---|
| laguna-s-2.1-free | yes | avg ~1.5s, p95 ~2s | structured-verdict, multi-choice, fast | reliable, follows format |
| ling-3.0-flash-fin-free | yes | avg ~1.3s | reasoning-caution | reliable, adds caution |
| nemotron-3.5-lightning-free | flaky | ~7s+ | slow-thinking, format-ignorant | ignores exact format, drops verdict in reasoning |
| nemotron-3-ultra-free | slow | ~41s | — | too slow for quorum |
| mimo-v2.5-free | rate-limited | — | — | 429 free-quota |
| deepseek-v4-flash-free | down | — | — | 400 "Model is unavailable" |
| muse-spark 1.3/1.2-contributor-free | yes (responses wire) | ~1.0s | **alive** — chat/completions 500 is wrong-wire artifact; use `/v1/responses` |

**Practical (updated 2026-09-12):** laguna is GONE from the live catalog — do not
plan quorums around it. **The free tier requires an `x-session-id` header** (any
UUID): without it the relay returns 400 `MissingSessionID` ("OpenCode's free tier
can only be used in OpenCode") and it does so for EVERY model, so a script missing
the header reports the whole tier down at once — read that as a header bug, not an
outage. All three tools (`zen_quorum.py`, `zen_tool_agent.py`,
`zen_models_profile.py`) now send one per process; the profiler was blind this way
and showed ALIVE (0) until 2026-09-12 (guarded by a unit test). muse-spark
1.3/1.2-contributor-free are alive (~1s) but ONLY on the responses wire;
chat/completions 500s there because the family never runs on that wire.
`deepseek-v4-flash-free` is UNAVAILABLE upstream (400 server_error).
`mimo-v2.5-free` answers on chat but 429s (`FreeUsageLimitError`) quickly on the
shared quota. Nemotron/deep thinkers are slow and ignore format — exclude from
frequent runs, keep only for deep one-off analysis at low cadence.

**Quorum prompt context (fixed 2026-09-12):** the runner used to cap the diff at
3 KB in the prompt and attach full source only for `.c`/`.h`, so a Rust or Python PR
was reviewed with no code at all and every model voted PARTIAL "cannot verify,
truncated". Caps are now `DIFF_FETCH_CAP`/`DIFF_PROMPT_CAP` (20/19 KB) with
`CODE_EXTS` covering c/h/rs/py/go/js/ts/php/pl/rb. Extend `CODE_EXTS` when the tree
gains a language. `verify_spots()`'s symbol index is still C-token oriented and
labels real Rust symbols `MADE-UP?` — that label is a grader blindspot, verify by
hand. Worked example: `engineering/zen-quorum-wasm-stop-the-rest-of-the-request-path.md`.

## 2026-09-06 — muse-spark verified alive (both free twins)

Both `muse-spark-1.3-contributor-free` and `muse-spark-1.2-contributor-free`
answer ~1.0s on the responses wire (keyless, empty `Authorization`). The
earlier 500s came from probing `chat/completions` — the relay routes this
family to `codex_responses`, so that probe never applied. Bare
`muse-spark-1.3` / `muse-spark-1.2` (no `-free` suffix) are the keyed twins:
keyless calls 401 there — that is expected, not downtime.

## 2026-10-03 — free tier now CLIENT-GATED (keyless access mostly dead)

Live probe (keyless, correct headers incl. `x-session-id`, per-request UUID):

| Model | Result |
|---|---|
| space-bunny-free | **200 — the only keyless-reachable free model** |
| ling-3.0-flash-fin-free, ling-3.1-flash-free | 403 `FreeTierError: OpenCode's free tier can only be used from within OpenCode` |
| longcat-2.5-preview-free, mimo-v2.5-free, mimo-v2.6-flash-free | 403 same |
| nemotron-3-ultra-free, nemotron-3.5-lightning-free | 403 same |
| muse-spark-1.3/1.2-contributor-free | 403 same on **both** wires (chat and `/v1/responses`) |
| deepseek-v4-flash-free | 400 upstream unavailable |
| jev-1.13-free | 500 Internal server error |
| fledge-alpha-free | 403 "not available in your country" |

- The gate is **not** header/UA based: `opencode/1.0.0` UA, `X-Title: opencode`,
  referer `https://opencode.ai` and extra client headers all yield the same 403.
  It reads as client attestation (signed session from the OpenCode client itself).
- New free ids appeared in the catalog since 09-12: `jev-1.13-free`,
  `mimo-v2.6-flash-free`, `space-bunny-free`, `longcat-2.5-preview-free`,
  `fledge-alpha-free`, `ling-3.1-flash-free` (catalog size 86).
- **Impact:** `zen_quorum.py`, `zen_tool_agent.py` and the 6-hourly
  `zen_models_profile.py` cron all assume keyless anonymous access — with one
  reachable model there is no quorum left. Do not read a mass 403 as "models
  down": it is one gate, tier-wide.

## Related docs
- `engineering/opencode-free-model-probe.md` — first availability probe (method)
- `engineering/zen-quorum-capget-decision.md`, `zen-quorum-pr-254.md`,
  `zen-quorum-pr-266.md` — worked examples
- Skill: `zen-quorum` (operating procedure)
