# zen-review PR #282 — http: release the application's buffers after compressing

_2026-09-08. Review of freeunitorg/freeunit#282. MERGED 2026-09-08 14:37 UTC._
_`fix/http-compression-multi-buffer` → master, +256/−43, 3 files. Fixes #177._

## What is wrong (fatal, not merely wasteful)
`nxt_http_comp_compress_app_response()` (`src/nxt_http_compression.c:170`) released
the app buffer it just compressed via `nxt_buf_free()` — `nxt_mp_free()`, a plain
pool free that NEVER runs `b->completion_handler` (`nxt_buf.h:239`). For port-mmap
buffers that handler is `nxt_port_mmap_buf_completion()` (`nxt_port_memory.c:159`),
the only thing that marks chunks free in `hdr->free_map`, drops the mmap_handler
reference and releases the `nxt_mp_retain()` on `port->mem_pool`. So **every
compressed response leaked its shared memory**. With `shm_limit` (100 MB default),
a worker exhausts buffers and stops answering — measured: 11 requests (~99 MB) and
a `TimeoutError` on the 11th.

## The fix
1. **Walk the chain, not just the head** — `nxt_port_mmap_read()` makes one
   `nxt_buf_t` per `nxt_port_mmap_msg_t`, linked into `r->out`, sync buffer at tail.
   The old version compressed the head and replaced the chain with one output, so
   anything behind the head was dropped and `ctx->clen_sent` counted only the head
   (which decides when the compressor is told it is finishing the stream).
2. **Free via the completion handler** — `nxt_work_queue_add(&engine->fast_work_queue,
   in->completion_handler, task, in, in->parent)` instead of `nxt_buf_free()`. Canonical
   idiom for port-mmap (same as `nxt_chunk_parse.c:336`, `nxt_websocket.c:105`,
   `nxt_port_socket.c:706`). `in->next` cleared because the handler walks the chain.
3. **Non-mmap buffers passed through** (trailing sync/last with no data; plain-mode
   not compressed).
4. **`in_len == 0 && !last` → release** instead of consuming zero bytes.
5. **Fail path re-attaches** the unconsumed input and the kept output so the caller's
   error path owns the whole chain.
6. **`NXT_HTTP_COMP_FLUSH_SLACK` (64)** headroom for the per-call flush marker that
   `bound()` does not promise.

## Verdict: APPROVE (merged)
- ✅ Balanced chain handoff; mmap buffers released via completion (fast_work_queue),
  consistent with `chunk_parse`.
- ✅ `clen_sent` now counts the full input length (the `last` flag is correct).
- ✅ Fail path does not lose memory — chain fully re-assembled.
- ✅ Symmetry on `cbytes == -1`: output freed, input re-attached.

## Tests (strong)
`test_php_compression_large_random_body` (parametrized gzip/br/zstd; 9 MB
incompressible; sha256 round-trip byte-for-byte; exactly one of Content-Length /
chunked framing) and `test_php_compression_shm_not_leaked` (15 requests >100 MB,
regression for #177). `raw_get` on a bare socket expresses "fail rather than blok
forever". Note in test: "Declining to compress is equally valid as long as the
encoding is not advertised".

## Notes
- Refs #177. Sibling reviews: zen-review-pr-281 (engine-quit tmcf UAF), pr-288
  (proto-death start RPC).
