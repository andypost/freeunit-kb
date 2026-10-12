---
title: Webhook reaction quantization
description: Batching GitHub webhook events into agent quanta: window, keys, supersession, record, first increment.
tags: [webhook, coalescing, batching, watermark, design]
status: draft
---

# Webhook reaction quantization

## 1. Where quanta form

**Nothing is stored today.** The route `platforms.webhook.extra.routes.freeunit-exp` in
`/opt/data/config.yaml` has no `coalesce` block, so every event passing the filters reaches
`_spawn_agent_run` — one full agent turn each.

The window is a **Hermes feature that already exists**: `gateway/platforms/webhook_coalesce.py`
(issue #92066), wired into `gateway/platforms/webhook.py` (`WebhookCoalescer`,
`validate_coalesce_config`, route key `coalesce`). Opt-in, agent-mode only (`deliver_only` /
`cron_job` + `coalesce` raises `ValueError` at startup). No new script for the window; a script
*is* needed for the durable record (§4).

Storage is `WebhookCoalescer._pending` (+ `_timers`) in memory on the aiohttp loop; the drainer
is `_timer` → `_settle` → `_spawn_agent_run` → `handle_message`. Window
`coalesce.window_seconds` (default 30), cap `coalesce.max_wait_seconds` (default 300), delay
`min(window, max(0, first_at + max_wait − now))`. The window restarts on every arrival; the cap
counts from the group's **first** event, so a stream cannot starve dispatch.

**While the agent is busy with a previous quantum:** the coalescer does not know a run is live.
Dispatch is `asyncio.create_task(self.handle_message(event))` and `webhook.py` has no semaphore,
so a settling quantum starts a second concurrent session instead of queueing. The window is the
only brake. (unverified: whether `handle_message` serializes per profile.) Durability is
process-local: `flush()` covers disconnect/shutdown; a hard kill loses the window.

## 2. Priority classes

Rule — *bypass if the event is a direct human address or a new report; normal window if the
reaction analyses an entity that can still change within seconds; daily if the value aggregates
across many entities.*

- **Bypass** (route `freeunit-exp`, label `direct-address`): `issue_comment` /
  `pull_request_review_comment` / `pull_request_review` whose `payload.comment.body` (resp.
  `payload.review.body`) contains `@freeunit-agent`; `issues` action `opened`. An unresolved key
  also bypasses by design — `enqueue()` returns `False`, the caller dispatches at once.
- **Normal window**: `pull_request` (opened / reopened / ready_for_review / synchronize),
  `discussion_comment`, `workflow_run` completed=failure.
- **Daily shape**: triage, digests, metrics — stay cron (three digests at 10:30 UTC).

## 3. Coalescing keys and supersession

`coalesce.key` is a bare dotted payload field or a `{...}` template; the group key is
`"{route}|{rendered}"`. Use `{{repository.full_name}}#{{number}}`. It carries **no event type**,
so an `issue_comment` and a `pull_request` on one number share a group — one entity, one quantum.
A route has one key, and `workflow_run` exposes no `number`, so it takes the immediate path.

Supersession: the newest arrival **replaces** the pending entry (payload, prompt, `delivery_id`;
`first_at` kept, `count` incremented) and restarts the timer, so only the latest dispatches. The
prompt gains "(Note: N webhook events for this item arrived in quick succession and were
coalesced)". Log: `[webhook] coalesced delivery <old> superseded by <new> (group=…, N events)`.

- **Push superseding a push**: same `pull_request.number` → earlier delivery cancelled, latest
  head wins (read the live head, not the payload sha).
- **Repeated workflow run on one commit**: superseded only on the same key; another run/PR number
  forms its own group. Dedupe on `(entity, head_sha)` in the record.
- **Comment arriving after the quantum formed**: before settle → merged; after settle → a
  separate run — the coalescer forgets dispatched groups. That gap is why §4 exists.
- **Restart replay**: `_record_delivery_id` matches `X-GitHub-Delivery` →
  `{"status":"duplicate"}`, but that map is in-memory.

## 4. Quantum brief and experience record

At the tick the agent gets the settled prompt plus the coalesce note. Add a brief from three
sources: **changed since last tick** — `git log "$prev..$head"` over the watermark in
`/opt/data/cron/change-state.json` (`head_sha`, `last_seen_ts`); **decided last time** — the last
record for the entity; **still open** — the carried-forward list. Never re-read the same commits.

Record: `/opt/data/cron/webhook-reactions.jsonl`, append-only, one line per quantum, under the
existing lock. Fields: `ts`, `route`, `entity`, `event`, `delivery_id`, `head_sha`,
`quantum_count`, `decision`, `open[]`, `posted_url`. The next tick reads the last N lines for the
entity plus the highest `head_sha`; that IS the brief. No new store.

## 5. Increment 1 (~1 day)

1. Add to the route: `coalesce: {key: "{{repository.full_name}}#{{number}}", window_seconds: 30,
   max_wait_seconds: 300}` (`validate_coalesce_config` fails on typos).
2. Create `/opt/data/scripts/webhook-quantum.sh`: `--brief` prints the watermark brief; after the
   run it appends one JSONL line.
3. Run: `bash /opt/data/scripts/webhook-quantum.sh --brief`.

Compare over 24 h: `[webhook] POST event=` count vs `[webhook] coalesce settled group=` count,
plus exhaustion rate. Baseline (2026-10-10 15:18 → 2026-10-11 21:33, ~30 h): 21 POST deliveries
(~0.7 turns/h), 538 `filtered` (434 `workflow_run`), 28 responses, 6 exhausted (21 %),
3 "not posted".

## Failure modes

| mode | defence |
|---|---|
| wedged tick | `max_wait_seconds` caps starvation; watchdog on older groups (unverified: none today) |
| lost event | `flush()` covers graceful disconnect only — accept ≤30 s loss; the watermark catches the entity next tick |
| duplicate after restart | write `delivery_id` to the JSONL, skip if seen |
| self-feedback | `freeunit-trusted-senders.txt` omits the bot, so its own comments fail the sender filter |

## Metrics for the Oracle Cloud stand

| metric | why | collectable today |
|---|---|---|
| turns per entity per day | unit cost of a quantum | yes — `[webhook] POST event=` in `logs/gateway.log` |
| events-in : dispatched | window effectiveness | partly — 538 : 21 today; `coalesce settled … events=N` after increment 1 |
| filtered ratio by type | filter cost | yes — gateway.log |
| exhaustion rate | 21 % of runs post nothing | yes — `grep -c 'Iteration budget exhausted'` |
| watermark lag per repo | compounding needs ticks to advance | yes — `change-state.json` `last_seen_ts` |
| time-to-comment | reaction latency | no (unverified) |
