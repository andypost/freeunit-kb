---
title: "Dead Functions After #if 0 Sweep: Historical Provenance and Triage"
status: verified
verified_at: 15ebdc23
type: concept
area: engineering
---

# Dead Functions After #if 0 Sweep: Historical Provenance and Triage

**Status:** verified at `15ebdc23`  
**Author:** Antigravity (Hermes Agent)  
**Issue:** [freeunit-exp#108](https://github.com/freeunitorg/freeunit-exp/issues/108)  
**Reviewed-by:** FreeUnitOPS (DeepSeek V4.1 Flash, Hermes Agent)

---

## 1. Overview & Scan Scope

Following the `#if 0` and dead code audit ([freeunit-exp#105](https://github.com/freeunitorg/freeunit-exp/issues/105)), the zero-call-site function classifier identified 28 symbols in the FreeUnit core (`src/` and `fuzzing/`) that possess zero call sites, zero function pointer registrations, and zero struct initializer references throughout the repository.

This report establishes the complete historical provenance of all 28 symbols from git history (originating in `nginx/unit`, archived HEAD `76b39e92`), dates their introduction and caller loss, documents the three multi-function dead clusters, and assigns definitive verdicts (`delete` / `keep` / `wire`).

---

## 2. The Three Verified Dead Groups

### Group 1: Connection-Level Proxy Engine (`src/nxt_conn_proxy.c`)
- **Symbols:** `nxt_conn_proxy` (`src/nxt_conn_proxy.c:100`), `nxt_conn_proxy_create` (`src/nxt_conn_proxy.c:60`).
- **History & Context:** Introduced by Igor Sysoev in commit `16cbf3c0` (2017-01-17) as `nxt_event_conn_proxy.c` and renamed in commit `7574c649` (2017-06-14). Comprising 987 lines and 28 internal static functions, this subsystem was an early prototype for connection-level TCP proxying.
- **Why It Was Never Wired:** When HTTP reverse proxy support was actively developed, it was implemented directly at the HTTP layer in `src/nxt_http_proxy.c`, tying into `nxt_http_request_t` and `nxt_conn_t`. The connection-level proxy subsystem was completely bypassed. Despite remaining compiled in `libnxt` / `unitd` for 9 years, it has 0 callers anywhere in the tree. Proxied workloads measured in `exp#105` run entirely through `nxt_http_proxy.c`.
- **Verdict:** `delete` (safe removal of unreferenced prototype file and its header declarations).

### Group 2: Dedicated Buffer Pool Subsystem (`src/nxt_buf_pool.c`)
- **Symbols:** `nxt_buf_pool_destroy` (`:173`), `nxt_buf_pool_file_alloc` (`:51`), `nxt_buf_pool_free` (`:132`), `nxt_buf_pool_mem_alloc` (`:11`), `nxt_buf_pool_mmap_alloc` (`:91`).
- **History & Context:** Introduced by Igor Sysoev in commit `16cbf3c0` (2017-01-17). Comprising 185 lines across `src/nxt_buf_pool.c` and `src/nxt_buf_pool.h`.
- **Why It Was Never Wired:** Conceived as a multi-tier buffer allocator supporting contiguous memory, disk files, and mmap regions. During Unit's core consolidation in early 2017, memory management was standardized around the unified `nxt_mp_t` pool (`src/nxt_mem_pool.c`), while I/O buffering standardized on `nxt_buf_t` (`src/nxt_buf.c`). `nxt_buf_pool.c` was abandoned before completion; no `.alloc` initializer or call site was ever wired. Only `#include <nxt_buf_pool.h>` remained in `src/nxt_main.h`.
- **Verdict:** `delete` (safe removal of 185 dead lines and include).

### Group 3: Unreferenced Header Inlines
- **Symbols:** `nxt_nvbcq_index` (`src/nxt_nvbcq.h:47`), `nxt_hash_insert` (`src/nxt_hash.h:28`), `nxt_hash_find` (`src/nxt_hash.h:19`), `nxt_hash_delete` (`src/nxt_hash.h:38`), `nxt_thread_event_engine` (`src/nxt_event_engine.h:557`).
- **History & Context:** 
  - `nxt_nvbcq_index` was introduced by Max Romanov in `a82cf4ff` (2020-08-11, "Circular queues implementations"). Circular queue operations throughout FreeUnit compute head/tail indices directly via bitmask arithmetic without invoking this wrapper.
  - `nxt_hash_*` inlines were introduced in `16cbf3c0` (2017-01-17). FreeUnit standardized configuration and route table hashing on the lock-free level hash table (`nxt_lvlhsh_t`, `src/nxt_lvlhsh.c`), leaving the simple open-addressing `nxt_hash_*` header functions with zero callers.
  - `nxt_thread_event_engine` was introduced in `16cbf3c0` (2017-01-17). Core event dispatchers pass `engine` directly or read `task->thread->engine`, bypassing this inline accessor.
- **Verdict:** `delete` (removes dead header clutter with zero compiler diagnostic impact).

---

## 3. Comprehensive Provenance Table (All 28 Symbols)

| # | Symbol | Location | Introduced | Written For | Caller Lost At | Old Repo (`76b39e92`) | Related PR/Issue | Verdict & Rationale |
|---|---|---|---|---|---|---|---|---|
| 1 | `nxt_nvbcq_index` | `src/nxt_nvbcq.h:47` | `a82cf4ff` 2020-08-11 Max Romanov | Helper for non-blocking circular queues index mask | Never had callers; queue loops use bitmask directly | Yes | none | **delete** — Dead inline header utility. |
| 2 | `nxt_buf_mem_init` | `src/nxt_buf.c:22` | `ba039157` 2017-01-27 Igor Sysoev | Initialize buffer memory struct fields | Never had callers; buffers allocated via `nxt_buf_mem_alloc` | Yes | none | **delete** — Unused buffer initializer. |
| 3 | `nxt_buf_pool_destroy` | `src/nxt_buf_pool.c:173` | `16cbf3c0` 2017-01-17 Igor Sysoev | Destroy custom buffer pool instance | Never had callers (Group 2 abandoned subsystem) | Yes | none | **delete** — Unwired subsystem. |
| 4 | `nxt_buf_pool_file_alloc` | `src/nxt_buf_pool.c:51` | `16cbf3c0` 2017-01-17 Igor Sysoev | Allocate file buffer from buffer pool | Never had callers (Group 2 abandoned subsystem) | Yes | none | **delete** — Unwired subsystem. |
| 5 | `nxt_buf_pool_free` | `src/nxt_buf_pool.c:132` | `16cbf3c0` 2017-01-17 Igor Sysoev | Free buffer back to buffer pool | Never had callers (Group 2 abandoned subsystem) | Yes | none | **delete** — Unwired subsystem. |
| 6 | `nxt_buf_pool_mem_alloc` | `src/nxt_buf_pool.c:11` | `16cbf3c0` 2017-01-17 Igor Sysoev | Allocate memory buffer from pool | Never had callers (Group 2 abandoned subsystem) | Yes | none | **delete** — Unwired subsystem. |
| 7 | `nxt_buf_pool_mmap_alloc` | `src/nxt_buf_pool.c:91` | `16cbf3c0` 2017-01-17 Igor Sysoev | Allocate mmap buffer from pool | Never had callers (Group 2 abandoned subsystem) | Yes | none | **delete** — Unwired subsystem. |
| 8 | `nxt_conn_proxy` | `src/nxt_conn_proxy.c:100` | `7574c649` 2017-06-14 Igor Sysoev | Run connection-level proxy state machine | Never had callers; HTTP proxy built in `nxt_http_proxy.c` | Yes | none | **delete** — Group 1 unreferenced proxy engine. |
| 9 | `nxt_conn_proxy_create` | `src/nxt_conn_proxy.c:60` | `7574c649` 2017-06-14 Igor Sysoev | Allocate connection proxy context | Never had callers; superseded by `nxt_http_proxy.c` | Yes | none | **delete** — Group 1 unreferenced proxy engine. |
| 10 | `nxt_conn_work_queue_set` | `src/nxt_conn.c:302` | `16cbf3c0` 2017-01-17 Igor Sysoev | Bind connection work queue pointers | `b9177d36` 2023-03-27 Andrew Clayton ("Remove a bunch of dead code" deleted caller `nxt_stream_source.c`) | Yes | none | **delete** — Last caller deleted in 2023. |
| 11 | `nxt_current_directory` | `src/nxt_runtime.c:1596` | `16cbf3c0` 2017-01-17 Igor Sysoev | Retrieve working directory as `nxt_str_t` | `e64494ba` 2017-08-26 Igor Sysoev ("Added configure option --pid=FILE" removed `rt->prefix` cwd call) | Yes | none | **delete** — Uncalled since 2017; prefix paths configured at build time. |
| 12 | `nxt_event_conn_write_limit` | `src/nxt_conn_write.c:415` | `16cbf3c0` 2017-01-17 Igor Sysoev | I/O write rate limiting calculation | `029942f4` 2017-02-22 Igor Sysoev ("I/O operations refactoring"); marked `/* Obsolete interfaces. */` | Yes | none | **delete** — Dead obsolete code explicitly marked since 2017. |
| 13 | `nxt_hash_delete` | `src/nxt_hash.h:38` | `16cbf3c0` 2017-01-17 Igor Sysoev | Delete element from simple hash table | Never had callers; `nxt_lvlhsh_t` used exclusively | Yes | none | **delete** — Group 3 unused inline hash helper. |
| 14 | `nxt_hash_find` | `src/nxt_hash.h:19` | `16cbf3c0` 2017-01-17 Igor Sysoev | Search element in simple hash table | Never had callers; `nxt_lvlhsh_t` used exclusively | Yes | none | **delete** — Group 3 unused inline hash helper. |
| 15 | `nxt_hash_insert` | `src/nxt_hash.h:28` | `16cbf3c0` 2017-01-17 Igor Sysoev | Insert element into simple hash table | Never had callers; `nxt_lvlhsh_t` used exclusively | Yes | none | **delete** — Group 3 unused inline hash helper. |
| 16 | `nxt_lib_stop` | `src/nxt_lib.c:636` | `16cbf3c0` 2017-01-17 Igor Sysoev | Terminate embedded Unit runtime | No in-tree caller; kept by Andy Postnikov in `d3d945c3` for external `libunit` ABI compatibility | Yes | none | **keep** — Documented ABI export with rationale comment at `src/nxt_lib.c:638`. |
| 17 | `nxt_list_next` | `src/nxt_list.c:79` | `16cbf3c0` 2017-01-17 Igor Sysoev | External iterator step for `nxt_list_t` | Never had callers; loop macro `nxt_list_each` used throughout codebase | Yes | none | **delete** — Unused chunked list iterator. |
| 18 | `nxt_listen_socket_pool_min_size` | `src/nxt_listen_socket.c:295` | `16cbf3c0` 2017-01-17 Igor Sysoev | Calculate memory pool size for listen socket | `6f2c9acd` 2017-03-09 Igor Sysoev ("Processes refactoring" dropped `ls->mem_pool_size` allocation in `nxt_cycle.c`) | Yes | none | **delete** — Caller lost in 2017 cycle refactor. |
| 19 | `nxt_port_destroy` | `src/nxt_port_socket.c:204` | `e57b95a9` 2017-02-01 Igor Sysoev | Destroy port socket and memory pool | Never had callers; port lifecycle managed by `nxt_port_close()` and `nxt_port_release()` | Yes | none | **delete** — Bypasses refcounting, unlinking, and RPC teardown. |
| 20 | `nxt_port_empty_handler` | `src/nxt_port.c:1402` | `b379dae8` 2017-02-22 Igor Sysoev | Fallback debug handler for port messages | Never had callers; processes register custom gate arrays | Yes | none | **delete** — Dead stub handler. |
| 21 | `nxt_port_quit_handler` | `src/nxt_port.c:427` | `b379dae8` 2017-02-22 Igor Sysoev | Fallback QUIT handler calling `nxt_runtime_quit` | Never had callers; router/controller use process-specific handlers (`nxt_signal_quit_handler`) | Yes | none | **delete** — Dead stub handler. |
| 22 | `nxt_runtime_event_engine_free` | `src/nxt_runtime.c:800` | `16cbf3c0` 2017-01-17 Igor Sysoev | Pop and free event engine from runtime queue | Never had callers; engines destroyed on thread exit | Yes | none | **delete** — Unused runtime engine teardown helper. |
| 23 | `nxt_runtime_log_file_add` | `src/nxt_runtime.c:1466` | `16cbf3c0` 2017-01-17 Igor Sysoev | Add and deduplicate log file in runtime | Never had callers; logging centralized in dedicated loggers | Yes | none | **delete** — Unused log file registry helper. |
| 24 | `nxt_thread_event_engine` | `src/nxt_event_engine.h:557` | `16cbf3c0` 2017-01-17 Igor Sysoev | Inline accessor for `thr->engine` | Never had callers; code references `task->thread->engine` directly | Yes | none | **delete** — Group 3 unreferenced inline accessor. |
| 25 | `nxt_thread_mutex_trylock` | `src/nxt_thread_mutex.c:149` | `16cbf3c0` 2017-01-17 Igor Sysoev | Non-blocking mutex acquisition | Never had in-tree caller; core concurrency API primitive | Yes | none | **keep** — Complete synchronization triad (lock / trylock / unlock) preventing deadlocks in non-blocking contexts; comment added at definition. |
| 26 | `nxt_thread_spin_trylock` | `src/nxt_spinlock.c:92` | `16cbf3c0` 2017-01-17 Igor Sysoev | Non-blocking spinlock acquisition | Never had in-tree caller; core concurrency API primitive | Yes | none | **keep** — Complete spinlock triad (lock / trylock / unlock) essential for non-blocking poll loops; comment added at definition. |
| 27 | `nxt_timezone_update` | `src/nxt_time.c:299` | `16cbf3c0` 2017-01-17 Igor Sysoev | Platform-specific `/etc/localtime` refresh (4 definitions) | Never called; timezone resolved at boot; time caching refactored to `nxt_thread_time` | Yes | none | **delete** — 4 platform definitions unwired for 9 years. |
| 28 | `nxt_var_field_get` | `src/nxt_var.c:185` | `45b89e32` 2022-07-14 Zhidao HONG | Array lookup for dynamic variable field | Never had callers; contains off-by-one bounds flaw (`index <= nfields`) | Yes | none | **delete** — Dead code with off-by-one indexing hazard. |

---

## 4. Triage Summary & Disposition

- **Total Symbols Evaluated:** 28
- **Delete Verdicts:** 25 symbols (comprising ~1,250 lines of dead code across `src/nxt_conn_proxy.c`, `src/nxt_buf_pool.c`, header inlines, and orphaned functions).
- **Keep Verdicts:** 3 symbols:
  1. `nxt_lib_stop` (`src/nxt_lib.c:636`): Preserved for external `libunit` C API compatibility.
  2. `nxt_thread_mutex_trylock` (`src/nxt_thread_mutex.c:149`): Preserved as fundamental non-blocking synchronization primitive.
  3. `nxt_thread_spin_trylock` (`src/nxt_spinlock.c:92`): Preserved as fundamental non-blocking spinlock primitive.
- **Wire Verdicts:** 0 (all evaluated candidates were either superseded by modern architectural layers or abandoned without consumers).
