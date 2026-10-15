---
title: "DeepSeek Harness (dsh) — web and headless operation"
description: "How the FreeUnit agent fleet uses dsh: the shared core behind every surface, the interactive web surface, the one-shot headless surface, credentials, permissions, deployment, and the dsh session parser."
format: "open-knowledge-format-v1"
updated: "2026-10-15"
maintainer: "andypost"
---

# DeepSeek Harness (`dsh`) — web and headless operation

Read 2026-10-15 against `deepseek-ai/deepseek-harness` `master` (the project's
user guides, CLI reference, and the `web-app`/`headless`/`base` bundle
references). The commands and defaults below are the project's documented
behaviour, not a measurement on our own bench box; a claim that matters is
re-run before it is relied on. The fleet-local facts (session parser, model
routing, authority rules) are on the harness side and linked at the end.

## One core, several surfaces

`dsh` is one launcher that boots a **profile**: an ordered stack of plugin
bundles plus a `cordis.patch.yml` overlay. `web` and `headless` are two
profiles over the same `dsh-base` core, so they share the model adapters, the
tool set, durable sessions, and the sandbox/approval policy. Only the surface
differs.

| Profile | Bundle that adds the surface | Opens a port? |
|---|---|---|
| `web` | `dsh-web-app` (HTTP server + browser UI) | yes, loopback `:3080` by default |
| `headless` | `dsh-headless` (one-shot runner) | no |
| `sdk`, `sdk-minimal` | JSON-RPC over stdio | no |
| `acp` | Agent Client Protocol over stdio | no |

The invoking directory is the default workspace root. `web`, `headless`,
`sdk`, `sdk-minimal`, and `acp` auto-initialize on first use from shipped
templates.

## Web surface

```sh
npx @deepseek-ai/dsh web           # published; or: dsh --profile web
dsh web --no-open --port 8080
dsh web --host 10.0.0.7 --public-url https://app.example/ui/ --trusted-host app.example
```

First run, in order:

1. **Set a model.** Settings → Models → a DeepSeek API key, or a third-party /
   custom OpenAI- or Anthropic-compatible provider. A change applies on the
   next request; no restart.
2. **Choose a workspace.** The composer stays disabled until one is selected.

Operational rules that are easy to get wrong:

- The printed `dsh web:` line carries a fresh process token. It is a
  credential; share the URL only with intended users. `printUrl: false`
  suppresses the line.
- `--public-url` is an **advertisement, not trust**. A browser that reaches
  the deployment under any other authority gets `403` until that authority is
  named with `--trusted-host`. The reverse proxy owns the external leg: keep
  the browser-facing `Host`, strip the mount prefix, forward upgrades, and
  rewrite the cookie `Path` (plus `Secure` when it terminates TLS).
- `--host` takes one concrete local IPv4/IPv6 address; a wildcard is refused.
- `--tls-cert` and `--tls-key` are one setting (both or neither). Files are
  read once and never renewed or watched; a change needs a listener reload or
  a process restart.
- SSH launches print the URL but do not open a browser.
- Neither `--public-url` nor the Host/Origin fence protects the port itself:
  restrict it to the trusted proxy or network.

Permissions are per-session **presets**: `workspace-write` (write under the
session workspace and the backend temp area) plus `ask`, and
`danger-full-access` plus `never`. `DSH_PERMISSION_MODE` sets the process
fallback. Stored General-settings permission changes affect later sessions,
not an already-open one.

## Headless surface — the automation surface

The surface for CI and for the 24/7 fleet: one task per process, no server, no
port, nothing left running.

```sh
dsh --profile headless "run the tests"
echo "summarize this diff" | dsh --profile headless
{ echo "Summarize these changes:"; git diff --stat; } | dsh --profile headless
dsh --profile headless --json "run the tests"
dsh --profile headless --session-id session-… "continue"
```

### Output contract

| Channel | Content |
|---|---|
| stdout | the final answer only (one line, no tool output) |
| stderr | `dsh: reasoning:` sections and, on failure, `dsh: <code>: <message>` |
| exit | `0` only for a completed turn; otherwise `1` |

A positional task is used verbatim and stdin is not read; put the whole prompt
in the pipe for piped input. An empty result prints an empty stdout line and
exits 1, so a loop should fail on empty output, not only on a nonzero exit.

### `--json`

Replaces the final-text stdout line with newline-delimited JSON: it opens with
`session` (id + cwd), carries `status`, `text`, `thinking`, `tool_call`, and
`tool_result` events, and closes with `final`. Projection facts:

- `text`/`thinking` are emitted when a step **commits**, not per token, so a
  retried attempt never reaches the stream.
- Every string except `final` is capped at 8 KiB and flagged `truncated`; one
  event line is capped at 32 KiB; payloads nested 64 levels or deeper are cut.
- A failure raised outside a turn emits `error` and no `final`. A turn that
  fails in-turn still ends with `final` (often empty). **Treat exit code 1 as
  the failure signal**, not the presence of `final`.
- The stream is a projection, not the session log.

### Resuming

`--session-id <id>` adopts a persisted session; an unknown id fails before the
task runs. Adoption is scoped: the session must match the recorded working
directory, be a root session (not a subagent or fork), run under a preset this
profile composes, and not already be live in the process.

### Credentials

The shipped headless profile **disables the managed credential store**, so
keys saved by the GUI are ignored. The order is launch environment, then
`<invocation cwd>/.env`, then `$DSH_HOME/.env`. An exported empty value shadows
the `.env` fallback. To restore stored authentication, re-enable the
`credentials`, `authorization`, and `deepseek-account` rows in the headless
profile patch.

### Permissions — the automation trap

Base defaults to sandbox `workspace-write` plus approval `ask`. Headless mounts
**no approval answerer**, so an `ask` falls through to `unavailable` and fails
closed: anything needing escalation is denied. In-workspace reads, writes, and
commands run fine. For an unattended job that needs wider access, the
documented lever is:

```sh
DSH_PERMISSION_MODE=danger-full-access dsh --profile headless "…"
```

That is what the project's own end-to-end tests use. It bypasses the sandbox,
so run it in a container or disposable checkout, never on a shared host
unattended.

## Consuming dsh sessions

The fleet normalizes dsh sessions with the harness parser, not by reading the
log by hand:

```
freeunit-harness/tools/session-extract/dsh.py   # newest session unless a path is given
```

It reads `~/.dsh/sessions/*/*/session.v4.jsonl.zstd`, decompresses with
`zstd`, and emits one line carrying cwd class, start/end, turn count, tokens
(in/out/cache-read), per-model call counts, tool counts, touched files, and
error markers. One trap is pinned in its header: an `assistant/message` line
holds usage twice (`data.usage` and a copy under `data.stream[].chunk.usage`);
read `data.usage` only. Before a long review or benchmark, checking a peer's
existing session through the parser is cheaper than repeating the work.

## Gotchas worth repeating

- One task per headless run; split multi-step work into separate runs.
- Default mode has no pre-token heartbeat: stderr is silent until the first
  reasoning delta.
- Reasoning goes to stderr and can be large and sensitive; route stderr to a
  controlled sink.
- A final background job may not settle into persisted history during
  teardown.
- Headless must be started through the `dsh` launcher, which owns the exit
  request.
- A source checkout must be built (`pnpm run build`) before `dsh web`; there
  is no source-serving fallback.

## See also

- `freeunit-harness/docs/agent-tools.md` — dsh next to agy, OpenCode, Codex:
  install, instruction files, skills, scripted use, cost, MCP, sandbox.
- `freeunit-harness/docs/model-routing.md` — which model gets which FreeUnit
  job; DeepSeek V4.1 Flash is the first-pass public-PR reviewer.
- `freeunit-harness/docs/agent-coordination.md` — the bus, the authority
  table, and where findings become KB pages.
