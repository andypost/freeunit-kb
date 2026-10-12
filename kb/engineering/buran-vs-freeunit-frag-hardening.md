---
title: How Buran solves the fragment/reassembly class — vs FreeUnit
description: Buran's BWP avoids the "hostile peer holds a reassembly slot / declares a huge length / rewrites shared state" class by construction (no peer-writable shared memory: atomic SOCK_DGRAM work queue + framed per-worker stream). Where it does reassemble (WebSocket) it bounds by size (max_message_size) and time (idle_timeout). The bounds map 1:1 onto FreeUnit #446/#447/#448/#505 — plus the time bound FreeUnit still lacks.
tags: [buran, port, frag, hardening, websocket, comparison]
status: analysis
updated: 2026-09-25
source: buran-project/buran (cloned 2026-09-25)
---

# How Buran solves the fragment/reassembly class

Prompted by @TuzelKO: *"посмотри как это решено в буране."* Verified against the
source (`/opt/data/repo-buran`, cloned 2026-09-25).

## The root difference: no peer-writable shared memory

Buran's IPC (BWP) is **not** shared memory. Two channels per worker:

- **Work socket** — `AF_UNIX SOCK_DGRAM`, shared across workers. A request is **one
  atomic datagram**: the kernel delivers it whole or drops it. There are **no
  "open streams held until the last fragment"** on the request path, so the exact
  bypass in #447 **cannot be expressed**.
- **Response stream** — a per-worker framed `UnixStream`: fixed 16-byte header
  (`FRAME_HEADER_LEN`) + `payload_len`, read with `read_exact`.

There is **no segment the peer can still write after the reader checked it**, so
the entire "read-once / rewrite-between-check-and-use / hold-a-slot" family is
**absent by construction** — not bounded, *absent*.

FreeUnit's port protocol puts a peer-writable mmap segment in the middle. That is
a deliberate zero-copy tradeoff, and it is exactly what *creates* the class
FreeUnit is now closing with bounds.

## Where Buran *does* reassemble — and how it bounds it

The only reassembly in Buran is **WebSocket messages (RFC 6455)**, owned by the
router (`crates/buran-router/src/ws.rs`). It is bounded three ways:

1. **Per-frame guard before buffering** (`parse_frame`): a data frame whose
   declared `len > max_message` is rejected *before* any allocation —
   *"The limit guards a single frame too, or a huge length would make us buffer it
   before the message-level check."* → `1009`.
2. **Accumulated-total guard** (`Decoder::next`): `frag.len() + payload.len() >
   max_message` → `TooBig`. The reassembled message is capped.
3. **Configured cap + time**: `max_message_size` default **1 MiB**,
   `websocket.idle_timeout` default **600 s** (`buran-config/src/schema.rs`).

So even where Buran reassembles fragments, the bounds are **size + time**, with the
declared length **never trusted for allocation**.

## Never trust a peer-declared length for allocation

### The response-stream frame reader (missed on the first pass — credit @TuzelKO)

`crates/buran-router/src/dispatch.rs:1110-1137` — the reader that pulls frames off a
worker's response stream has a **dedicated** anti-oversized-frame defense, in three
layers:

1. **Per-frame cap, enforced before allocation.**
   `const MAX_FRAME_PAYLOAD: u32 = 64 * 1024 * 1024;` — *"Hard ceiling on a single
   response-stream frame payload… this only stops a buggy/hostile worker from making
   the router buffer up to **4 GiB from one framed length**. Over it, the stream is
   failed and the worker's requests fall out with the reader."*
   ```rust
   if header.payload_len > MAX_FRAME_PAYLOAD {
       return Err(std::io::Error::other(format!(
           "worker frame payload {} exceeds the {MAX_FRAME_PAYLOAD}-byte limit", ...)));
   }
   ```
2. **Incremental read — the declared length is never pre-allocated.**
   ```rust
   // Grow the buffer as bytes actually arrive rather than pre-allocating the
   // worker-declared length: a bogus payload_len (buggy worker) then hits EOF
   // instead of committing the whole capped size of zeroed memory.
   let want = u64::from(header.payload_len);
   let mut payload = Vec::new();
   if stream.take(want).read_to_end(&mut payload).await? as u64 != want {
       return Err(std::io::Error::from(std::io::ErrorKind::UnexpectedEof));
   }
   ```
   A short read (peer died mid-frame) → `UnexpectedEof`; the reader task ends and
   every request demuxed on that stream falls out together — no orphaned state held.
3. **Tests pin it:** `read_frame_rejects_oversized_payload_len`,
   `read_frame_accepts_payload_at_the_cap_boundary`.

And in the WS decoder: `parse_frame` guards a frame's declared length against
`max_message` **before** `to_vec()`; `read_frame` in the bench tool carries the same
"grow with the data" comment.

So the anti-fragmentation defense is **explicit and layered** — cap (per-frame, before
alloc) + incremental read (no trust) + total cap (WS message) — not merely implied by
the transport. This is exactly the principle behind FreeUnit **#505** (bound the id
before growing the array) and #447 (bound the reassembly).

## The rest of Buran's request-path bounds

| Stage | Buran mechanism |
|-------|-----------------|
| Headers | `MAX_HEADER_BYTES = 32 KiB`, `MAX_HEADERS = 64` → **431** |
| Body | `read_exact_body` with a **per-read timeout** *and* a **`min_rate` floor** (slow-POST / RUDY defence) |
| In-flight | `pool.try_reserve()` → **503 before** a large body is spilled; bounded queue, reject on pressure |
| Writer loops | `read_exact` on a fixed header — no peer-controlled loop counter, plus timeouts |
| Idle | `http.idle_timeout` (180 s), `websocket.idle_timeout` (600 s) |

## Mapping onto FreeUnit's wave

| Threat | Buran | FreeUnit |
|--------|-------|----------|
| Unbounded header | 32 KiB / 64 headers → 431 | **#446** |
| Fragment memory DoS | `max_message` (1 MiB), per-frame **and** total → 1009 | **#447** (bytes) |
| "Hold a slot forever" | no SHM slots (atomic datagrams); WS bounded by size+idle | **#447 evict** (partial — no timeout) |
| Length / id bomb | **`MAX_FRAME_PAYLOAD` = 64 MiB** per frame, checked **before** alloc; then "grow with the data"; WS `max_message` per-frame guard | **#505** |
| Bad-state spin | fixed `read_exact` + timeouts | **#448** |
| Slowloris / dribble | `read_timeout` **+ `min_rate`** | ❌ **missing** |
| Incomplete-stream lifetime | `idle_timeout` everywhere | ❌ **missing** (evict is pressure-only) |

> **#505 vs `MAX_FRAME_PAYLOAD` — same principle, different object.**
> Both = "bound a peer-supplied quantity before allocating," and both share the
> exploit *shape* (one field in a message → unbounded allocation). But #505 bounds a
> **segment id — an index** into a peer-grown array (id 1e8 → 1e8 slots); the cap
> bounds a **length** (a byte count → one buffer). The *index* variant exists only
> because of the SHM segment array, so Buran has no direct analog of it. FreeUnit's
> direct *length* siblings of `MAX_FRAME_PAYLOAD` are **#446** (headers → 431),
> **#593f9f5c** (request length vs the app protocol), **#447** (fragment bytes). And
> the incremental-read layer maps to **read-once #445/#468**, not to #505.

## Slow-transfer defense (slowloris / slow-POST / RUDY)

Buran answers "a client that *deliberately* sends very slowly" with **three different
mechanisms**, because one is not enough:

1. **Headers (slowloris) — a total wall-clock budget, *not* a per-read timer.**
   `header_read_timeout` (default 30 s) is *"a single wall-clock budget for the WHOLE
   header block once the first byte arrives (not a per-read idle timer — that would
   let a client dribble bytes forever; slowloris)."*
   Code (`http1.rs`): `header_deadline: Option<Instant>`; while `buf` is empty the
   conn may idle (`idle_timeout` 180 s) until the first byte; on the first byte
   `deadline = now + header_timeout`; each read uses the *remaining* budget; spent →
   close quietly. Dribbling one byte per 29 s for 10 minutes **fails** (total capped
   at 30 s).
2. **Body (slow-POST / RUDY) — per-read timeout + a sustained `min_body_rate` floor.**
   `min_body_rate` default **256 B/s**, with a **grace window** (= `body_read_timeout`
   for TCP slow-start / setup). `read_exact_body` bounds each read with
   `timeout(read_timeout)`, then `body_rate_ok(received, elapsed, grace, min_rate)`
   must hold. Comment: *"the min_body_rate floor additionally cuts a slow-but-moving
   dribble (slow-POST / RUDY) that inflates Content-Length to buy a long hold."* Both
   are needed: a per-read timeout alone does **not** catch "one byte just before each
   deadline."
3. **Keep-alive idle** `idle_timeout` (180 s); **writes** `send_timeout` (30 s).

### FreeUnit's asymmetry (actionable)

FreeUnit has both knobs (`nxt_socket_conf_t.header_read_timeout` /
`body_read_timeout`) but wires them differently (`src/nxt_h1proto.c`):

- **Header state: one-shot** — `timer_data = offsetof(…, header_read_timeout)`, **no
  `timer_autoreset`** → a single budget for the header block → **slowloris-safe**, same
  shape as Buran. ✓
- **Body state: `timer_autoreset = 1`** — `timer_data = offsetof(…, body_read_timeout)`
  → a **gap timer between reads** (the nginx `client_body_timeout` semantics). A client
  sending one byte just before each deadline holds the connection **indefinitely**.
  There is **no rate floor**. ✗

So FreeUnit's body path is exactly the case Buran's `min_body_rate` closes. **Concrete
gap to add:** a sustained minimum body throughput (with a grace window) — or a
total-body budget — alongside `body_read_timeout`. Buran's `body_rate_ok()` is the
reference implementation.

## Conclusion

- **Buran closes the class by construction** — no peer-writable SHM. FreeUnit must
  close it by **discipline** (read-once + count/bytes/**time** bounds), because the
  SHM port is a chosen tradeoff.
- Buran's bounds map **1:1** onto #446/#447/#448/#505 — the wave is converging on
  the same shape Buran already has.
- **Two things Buran has that FreeUnit's wave still lacks**, and they are exactly
  the "time" axis: (a) an **idle timeout** on incomplete reassembly (evict is
  triggered by pressure, not time); (b) a **`min_rate` floor** alongside the body
  read timeout (a slow-but-moving dribble is not caught by a timeout alone).
