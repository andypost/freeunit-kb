# Ops / environment facts (SOUL environment quirks)

_2026-09-03. Cross-cutting facts about the runtime environment. Kept OUT of the
small persistent memory (MEMORY.md) so memory stays navigation-only; these go
through the KB graph so a query like "why did yt-dlp / uv / telegram fail" finds
them with relevance, not by recall._

## YouTube / yt-dlp
- **Blocked from Hetzner cloud IPs**: `yt-dlp` hits an anti-bot "Sign in to
  confirm you're not a bot" wall on the server (Hetzner IP ranges are flagged).
- Workaround: pass `--cookies <file>` (a logged-in YouTube cookies.txt) and/or
  `--proxy <host:port>` to route around the IP fingerprint. Without one of these,
  downloads from the server fail.
- Applies to any tool that fetches YouTube (yt-dlp, ytarchive, youtube-transcript
  helpers). Local (non-Hetzner) IPs usually don't hit the wall.

## uv (python package manager)
- Prefer `uv` over `pip` for any Python work in this environment.
- `python3` here is **3.14.7**; uv resolves packages from PyPI, not apt.
- Cache: `UV_CACHE_DIR=/tmp/uv-cache` if the default cache dir is unwritable
  (container may restrict writes under the user's home). `uv cache clean` to
  reclaim space.
- Some tools are Rust binaries not on PyPI: `uv tool install ast-grep` fails with
  "not found in package registry" (ast-grep is a cargo/crates.io tool, not pip).
  For those use the crates/native route, not uv.

## Telegram output quirks
- Config: `platforms.telegram.extra.rich_messages: true`, `topics: true`,
  `silent_restart: true`, `disable_link_previews: true`, `guest_mode: true`.
- **No tables in the Telegram group** — Telegram renders markdown tables
  inconsistently/breaks them. Use bullets or labeled lines (memory rule + seen
  in digests). Rich markdown is on but the (upstream) reader may drop/truncate
  richer markup on incoming messages.
- `require_mention: true` — the bot only acts on an explicit @mention in a
  group/topic; DM is always on.
- **Never echo tool output in the group.** Only clean result text. (Andrey rule.)

## Misc environment
- **Scaleway benchmarks**: paramiko (no ssh prompt), per-min billing, instances
  created/owned only by Andrey. Details: `engineering/scaleway-benchmark-plan.md`.
- Scripts for cron run from `~/./scripts/` (i.e. `/opt/data/scripts/`); `script`
  cron field = **filename only**, args via a wrapper. `model` for a cron job can
  only be pinned via CLI (`hermes cron edit`), not the agent cron tool.
- `glab` (GitLab) global config targets `gitlab.com`; for aports use
  `GITLAB_HOST=gitlab.alpinelinux.org` per-invocation (do NOT mutate the global
  config). Keyless public reads work; `/notes` (comments) need a token.

## Container resource limits (memory)

- Container memory cap is **512 MiB** (`memory.max`); the gateway itself sits at
  **~300–320 MiB** RSS. The host is small (1.9 GiB total, swap ~600 MiB of 1 GiB
  used), so the cgroup is routinely pinned at the ceiling (`memory.events: max`
  in the hundreds).
- Symptom of a spike: the gateway dies **uncleanly — SIGKILL, no shutdown path**
  (`exited UNCLEANLY (no exit path ran — SIGKILL / OOM / VM death)`), sessions
  lose their turn, gateway restarts every few minutes and the restart-loop
  breaker trips. Container-internal `oom_kill` stays **0** — the kill comes from
  the host, so the gateway log cannot explain it.
- **Rule: run heavy local reads through `tools/memcap.py <MiB> <cmd>`** (sets
  RLIMIT_AS/RLIMIT_DATA on the child, prints peak RSS + wall). A runaway command
  then dies alone instead of taking the gateway down.
- **Measured (cap 96 MiB)**: naive `read().splitlines()` of a 20 MB JSONL →
  `MemoryError`; streaming line iteration → ok, **7.2 MiB** peak. Naive
  `sqlite3 ... fetchall()` over `state.db` messages (310 MB db) → `MemoryError`
  at 88 MiB peak. So: never `fetchall()` a big table, never `read()` a big file —
  iterate, filter in SQL, or chunk.
- Caps apply to virtual address space, so they are stricter than RSS — expect
  failures before RSS alone would suggest trouble.

## kTLS in this container — SOLVED: set the TLS ULP first (2026-10-11)

Earlier entries here claimed kTLS was unavailable and then that the cause was undecidable. Both were
wrong, and the reason matters more than the error: **`setsockopt(SOL_TLS, TLS_TX, …)` without the TLS
ULP never reaches the TLS code at all**, and the socket layer answers the generic ENOPROTOOPT (92) —
the same errno an unknown level `31337` returns, which is why the negative looked like a kernel
property.

Measured locally on kernel `6.8.0-136-generic`, Alpine 3.25 container, `tls` module loaded:

```python
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
c = socket.create_connection(srv.getsockname()); p, _ = srv.accept()
c.setsockopt(socket.IPPROTO_TCP, TCP_ULP, b"tls\x00")   # documented step, must be ESTABLISHED
c.setsockopt(282, 1, crypto_info)                       # SOL_TLS, TLS_TX -> accepted
c.sendall(b"marker"); raw = p.recv(4096)
# -> b'\x17\x03\x03\x00-' (application_data record), plaintext not visible in transit
```

`TCP_ULP=tls` is itself refused with **107 ENOTCONN** on an unconnected socket — `tls_init(sk)` (the
ULP's `.init`) requires `TCP_ESTABLISHED` before it creates the `tls_context` and swaps `sk_prot`.

**Consequence:** kTLS is exercisable both here and on GitHub-hosted runners (confirmed on
ubuntu-24.04 / kernel 6.17 and ubuntu-22.04 / kernel 6.8). The `auto/ktls` build probe and the
runtime probe are both viable; the earlier "container cannot do this" line is retracted.

## Context7 (library/kernel docs lookup) — keyless, works from here

Verified 2026-10-11 from this container, no MCP server and no API key needed:

```
curl -s "https://context7.com/api/v1/search?query=<url-encoded query>"          # library search -> JSON {results:[{id,title,totalTokens,stars,...}]}
curl -s "https://context7.com/api/v1/<id-without-leading-slash>?type=txt&topic=<topic>&tokens=<n>"   # docs text for one library
```

- `id` comes with a leading slash (`/websites/kernel_doc_html`); drop it in the docs URL path.
- Corpora that answered well: `/websites/kernel_doc_html` (Linux kernel docs — kTLS, TLS_TX/TLS_RX, sendfile). Returns real doc excerpts with `Source:` URLs, so a claim taken from it is citable.
- Corpus that did NOT answer: `/openssl/openssl` — zero hits for `SSL_sendfile`, `kTLS`, `TLS_TX` on every topic tried (its index is mostly QUIC design docs and man sources). Do not assume Context7 covers OpenSSL APIs.
- Relevance ranking is weak: a `topic=ktls` query mixes in livepatch and list macros. Grep the returned text for the term you actually need instead of trusting the order.
- **Size is driven by `--tokens` and nothing else caps it** (measured on `kernel_doc_html`, topic "TLS_TX sendfile"): 500 tokens → 2 095 B / 62 lines; 2 000 → 7 383 B / 206; 4 000 → 12 457 B / 376; 8 000 → 21 681 B / 675; 16 000 → 39 113 B / 1 202. That is **2.4–4.2 bytes per requested token**, so a large value dumps a whole corpus into the context. `--grep` cut the same 4 000-token answer from 12 457 B to 3 806 B (3.3×).
- **The wrapper is the guard**: `--max-lines` (120) and `--max-bytes` (12 000) are enforced, `--tokens` is clamped at 20 000, every truncation prints the original size on stderr, and each call ends with `returned N bytes / M lines`. Raise a cap only deliberately.
- No MCP server is configured in this Hermes profile; the plain HTTP API is enough for one-off lookups. If a durable tool is wanted, add Context7 as an MCP server rather than wrapping curl.

## Related
- `engineering/scaleway-benchmark-plan.md` — benchmark infra (Scaleway, per-min).
- `engineering/zen-review-architecture.md` — gh_cache/zen_review (GitHub+GitLab).
