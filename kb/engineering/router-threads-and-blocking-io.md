# FreeUnit: router threads, and the one blocking write on the request path

**Created:** 2026-10-03
**Trigger:** TuzelKO voice memo (forwarded by Andrey): "Unit's incoming-connection
handler is single-threaded — a crafted request can stall it and the socket just piles
requests up". Premise check against the tree, plus what is actually blocking.
**Pinned revision:** verified against `origin/master` `ac2f2d29` (2026-10-03);
line numbers cited as of that tip (the local checkout can be weeks stale — read
`git show origin/master:<path>` for state, never the working tree alone).

## 1. The premise is outdated: the router has been multi-threaded since 1.33.0

- Feature "make the number of router threads configurable" — `Changes with Unit
  1.33.0` (2024-09-17), commit `57c88fd4` (Andrew Clayton, 2024-08-12).
- Config: `settings.listen_threads` → `nxt_router_conf_t.threads` (`src/nxt_router.c`,
  conf map). Default **`nxt_ncpu`**; validator allows `>= 1` only
  (`nxt_conf_vldt_listen_threads`), so `listen_threads: 1` still gives the old
  single-threaded router on demand.
- Per thread: one event engine (one `epoll`) — `nxt_router_thread_create()` →
  `nxt_router_thread_start()` → `nxt_event_engine_thread_adopt(engine)`.
- Accept model: **one listening fd shared by all engines**, no `SO_REUSEPORT` anywhere
  in the tree. Each engine registers its own listen event on the same fd
  (`nxt_router_listen_socket_create()` → `nxt_listen_event(task, ls)`, `ls->count++`
  under `router->lock`), so the kernel wakes one acceptor per connection.
- Engine count changes on reconfigure: `nxt_router_engines_create()` keeps, adds
  (`NXT_ROUTER_ENGINE_ADD`) or deletes engines to match `threads`.
- Known cost of the shared-fd choice (code comment in the listener-close path): the
  listening FD stays bound until the drain of accepted connections completes, so
  re-adding the same address while an old listener drains fails with `EADDRINUSE` in
  the main process — a visible, retryable config error.
- Tests exercise it: `test/test_listen_threads.py`, `test/test_conn_recycle.py`,
  `test/test_process_abrupt_teardown.py`, `test/test_process_shm_oosm.py`.
- `/status` aggregates per-engine counters (`accepted_conns`, `idle_conns`,
  `closed_conns`, `requests`) into one report — no per-thread numbers, so "one engine
  stalled" is not observable from the API as it stands.

## 2. App side stays one-request-at-a-time per process

- `threads` / `thread_stack_size` exist for python, perl and java app confs — **not**
  for php (`nxt_conf_vldt_php_common_members` carries no `threads`).
- So PHP parallelism = process count: `processes`/`spare`, idle ports + `idle_timeout`
  (default 15 000 ms) reaper QUIT. See `app-process-lifecycle`.

## 3. Parsing cannot be stalled; the body spill can

- Headers: incremental parser, bounded by `large_header_buffer_size` (8 KiB) ×
  `large_header_buffers` (4) — a crafted header burst cannot wedge the loop.
- Body: `body_buffer_size` 16 KiB, `max_body_size` 8 MiB (`src/nxt_router.c`).
- **A body larger than `body_buffer_size` is spilled to a temp file with a SYNCHRONOUS
  `nxt_fd_write()` from inside the read handler** (`src/nxt_h1proto.c`: 1036, 1056,
  1170, 1216), both for a declared Content-Length body and for the chunked path; the
  temp file is created with `mkstemp()` + `unlink()` per request, default directory =
  the runtime tmp (`task->thread->runtime->tmp`) unless `body_temp_path` is set.
- For a regular file `O_NONBLOCK` is a no-op, so the router thread waits on the disk.
  Consequence: a slow / saturated / network `body_temp_path` stalls the accepting
  engine holding that connection, and N concurrent large uploads (max 8 MiB each) can
  stall as many engines as there are threads. The stall is local to the filesystem —
  not a remote attack on the parser.
- Contrast: file *sending* already has a thread-pool escape (`nxt_thread_pool_post()`
  in `nxt_event_conn_job_sendfile.c`, upstream code). The body spill is the remaining
  synchronous disk write on the loop.
- KB context: `event-loop-alternatives` already concludes io_uring's credible use is
  file I/O, not the socket loop — this is that same conclusion arriving as a bug.

## 4. Plan

1. **Measure before changing**: stand with `listen_threads: 1` vs `ncpu`, `body_temp_path`
   on an artificially slowed path, N concurrent >16 KiB uploads; assert whether other
   connections stall. Verdict from numbers, not from reading.
2. If confirmed, move the spill off the loop: thread-pool job (pattern exists —
   `c->block_read/block_write` + return to the loop, as in the sendfile job) or an
   asynchronous write mechanism (io_uring is absent from the tree; that would be new
   surface, and 2 already has an in-tree precedent).
3. Hygiene: per-request `mkstemp` + `unlink` on the router's hot path — worth a cost
   reading.
4. Observability: expose per-engine counters (or a max-per-engine latency) so a stalled
   engine is visible; today `/status` sums them.
5. Docs: the feature that answers "the router is single-threaded" is documented poorly —
   the OpenAPI description for `settings` renders the option as "n", and CHANGES states
   the feature without the model.

## 5. Slow-client (slowloris / slow-POST / RUDY) axis — where FreeUnit stands

- Threads are NOT what a slow client holds: the loop is event-driven. It holds
  (a) a connection + router memory, (b) an **app worker process** — the request is
  dispatched to the app as soon as the headers parse
  (`nxt_router_process_http_request()` → `nxt_router_app_port_get()`), with the body
  streamed afterwards, and (c) disk/memory for the spill. A router thread is held only
  during the synchronous temp-file write.
- **A per-engine connection ceiling DOES exist and is hardcoded**: `rt->engine_connections
  = 256` in `nxt_runtime_conf_init()` (`src/nxt_runtime.c`), copied to
  `engine->max_connections`; `nxt_conn_accept_alloc()` admits only while
  `engine->connections < engine->max_connections`, and on reaching it the listener is
  left unarmed and idle connections are closed to make room. Not configurable, not
  reported, no log line (issue #539). So eroding capacity "to the accept ceiling" needs
  only a few hundred held connections — the attacker's cost stays one packet in ~29 s.
- Header path is already slowloris-safe: `nxt_h1p_header_parse_state` arms
  `header_read_timeout` with NO `timer_autoreset` → one wall-clock budget for the whole
  header block (Buran's shape).
- Body path is the hole: `nxt_h1p_read_body_state` arms `body_read_timeout` WITH
  `timer_autoreset = 1` → a gap timer between reads; one byte before each deadline holds
  the connection (and the app worker) forever. No rate floor. This is Buran's
  `min_body_rate` gap exactly.
- Open fix: PR **#508** `http: add body_min_rate and send_min_rate`
  (branch `fix/slow-transfer-min-rate`, author andypost, updated 2026-09-28, non-draft)
  — the port of Buran's `min_body_rate`; security/DoS → belongs in patch 1.36.2.
- Still missing after #508: an idle **timeout** on held / incomplete resources
  (FreeUnit's fragment evict is pressure-only; Buran bounds by size + time everywhere)
  and admission control before a body is spilled (Buran's `pool.try_reserve()` → 503
  BEFORE buffering; FreeUnit accepts the request and may answer 503 only later).
- From `buran-adoptable-changes`, same "slot held forever" family: worker handshake
  timeout (a worker that never sends READY parks its slot) and crash-streak backoff;
  INI-newline rejection is a one-hour item.
- Correction for the memo's second half: making the router *more* multi-threaded does
  nothing for this class — every thread suffers the same hold. What helps is time +
  rate + admission bounds, plus getting the temp-file write off the loop.

## 6. Mimic half of the memo (separate, not a FreeUnit fact)


TuzelKO's plan — replicate the socket-listening isolate across all threads, each with
its own loop, all taking from one socket (Node cluster shape) — is still an OPEN item in
the Mimic tree ("isolates as a language verb"; Tavern's decided part is many loop threads
with one `epoll` each, isolates placed by the engine). The decision it forces is the same
one Unit already made: **one shared listening fd, no `SO_REUSEPORT`** — with Unit's own
price attached (config reload waits for the accept drain; rebinding the same address
fails `EADDRINUSE` until then).
