# musl (Alpine) allocator CPU gap — 12–17% per request

Upstream report: `freeunitorg/freeunit#688` (opened at pin `8492d5ee`, 2026-10-13;
**kept open on purpose** — the remaining items need the tracker).
Workbench task: `freeunitorg/freeunit-exp#40`.
Watcher: cron `76c80d0cdc88` (`freeunit-688-watch.py`, `15 */6 * * *`),
state `/opt/data/state/freeunit-688-watch.json`.

## The finding

FreeUnit on Alpine 3.24 (musl 1.2.6) costs **12–17% more CPU per request** than
Debian 13 (glibc 2.41). All of the extra is **system** time; user time is equal
within noise.

| workload | variant | user | system | total | faults |
|---|---|---|---|---|---|
| hello arm64 | Alpine | 43.8 | 81.0 | 124.8 | 4.46 (router) |
| hello arm64 | Debian | 46.3 | 64.4 | 110.7 | 0.10 (router) |
| Drupal arm64 | Alpine | 3012 | 1220 | 4233 | 199.9 (app) |
| Drupal arm64 | Debian | 3274 | 496 | 3770 | 1.4 (app) |

Independent re-run of the Drupal pair: **11.7% less server time on Debian**,
95% CI half-width 1.41%, null band 3.1%.

**Mechanism.** mallocng maps a **group** per size class and unmaps it when the
last live slot in it is freed; glibc keeps freed chunks in its arena. A 4 KiB
allocation therefore costs `mmap` + `munmap` plus its group's page faults. The
57 344-byte maps are `14 * 4096` — the group for the 4 KiB class, not "the 4096
cluster plus alignment". Kernel profile on Alpine: `do_user_addr_fault` 2.08%,
`flush_tlb_mm_range` 1.70% (both below 0.4% on glibc).

## The fix list (seven) and its state (2026-10-14)

| # | fix | state |
|---|---|---|
| 1 | per-thread cluster cache for pool clusters | **merged** `cc94deb2d` (PR #693) |
| 2 | PHP SAPI opens the script once (`access()`, not `fopen()`) | **merged** `1edda3a07` (PR #706) + `954fbc865` (PR #707) |
| 3 | return port read buffers to `port->free_bufs` | **already in master**; the bound was built and measured **neutral** |
| 4 | request object inside the first pool cluster | **rejected** — page-size variant measured, no change |
| 5 | Alpine packaging: jemalloc or mimalloc | **measured, not decided** |
| 6 | php-src: `closelog()` only after `openlog()` | **reported** php/php-src#24308 |
| 7 | musl: skip the second `F_SETFD` after `open(O_CLOEXEC)` | **closed** — it is musl's own call |

### Fix 1 — PR #693, merged `cc94deb2d` (2026-10-14)

- Router `mmap`/request falls **39% arm64** (0.82→0.50) and **35% amd64**
  (0.70→0.45); router page faults −41% / −36%; the router keeps 44–56 KiB more.
- `hello` arm64 116.9 → 111.3 µs: clears the 4.7 µs null band by ~1 µs — real
  but small. On the shared amd64 host there is no CPU claim.
- **Drupal: no change** — the Drupal churn is not in the router (see below).
- Cache caps: 32 total, 16 of one size.

### Fix 2 — PR #706 + #707, merged

Correction to the first text: on Alpine the pre-change script sequence was one
`openat` plus **two** `fcntl(F_SETFD)`, not four; on glibc the same sequence has
**no `fcntl` at all**, so the two builds differ in the sequence itself and "one
fewer call" does not hold.

### Fix 3 — already in master

Both read paths hand the buffer back (`src/nxt_port_socket.c:1973`, `:2283`).
The missing bound was built (counter + `nxt_mp_free()` above four buffers) and
measured **neutral**: 257 416 vs 256 624 kB tree VmHWM, 35 580 vs 35 584 kB
cgroup `memory.peak`, faults 0.913 vs 0.878/req — inside the repeat spread. The
list is bounded by messages in flight on the port, not by requests served.

### Fix 4 — rejected

`sizeof(nxt_http_request_t)` = 1592 (allocation block 1632 incl. the 40-byte
`nxt_mp_block_t` header; 1600 with OTel; **1576** after PR #705 moved
`num_inline_fields` in four router structures). It is above the 512-byte pool
page, so `nxt_mp_alloc()` sends it to `nxt_mp_alloc_large()`. Bumping the pool
page to 2048 changes nothing measurable: same memory, same faults, `mmap` 0.0008
per request in both builds. The page size is not the lever.

### Fix 5 — allocator (the decision left)

The **only** thing that moves the Drupal gap (which lives in the PHP process /
libsqlite3), and it must reach the **router and the workers**, not only PHP
(`LD_PRELOAD`, or a linked allocator — the PHP worker is a fork of `unitd`).

`hello`, Alpine aarch64, 4 PHP workers, `wrk -t2 -c16 -d10s`, cgroup `cpu.stat`,
µs/req total:

| allocator | median | spread | faults/req |
|---|---|---|---|
| musl mallocng | 74.2 | 66.6–81.7 | 0.99–1.21 |
| jemalloc 5.3.0 | **60.7** | 58.9–62.2 (7 cells) | 0.028–0.030 |
| mimalloc v3.5.4 release (built) | **58.4** | 45.8–63.3 | 0.025–0.030 |
| mimalloc 2.2.7 / v3.5.4 secure (Alpine pkg) | 62.1–62.9 | | 0.023–0.031 |

- **Correction (2026-10-14):** the Alpine package ships only mimalloc **2.2.7
  secure**; building **v3.5.4 release** from source gives the better median and
  best cells 24% below jemalloc, **but** the earlier "jemalloc recovers more than
  mimalloc" reading does **not survive** the larger sample (mimalloc's spread is
  wider; the two are within noise in the alternating round).
- **Drupal (8 workers):** both close the reported gap and are **equal within
  spread** (jemalloc 3797–3960 µs, mimalloc 3833–3925 µs, against mallocng
  4660–4709). The difference is in **faults**: mimalloc 2.5–2.7/req vs jemalloc
  17.1–18.9 vs mallocng 205.
- **Memory is the price** (Drupal, cgroup): mallocng frugal — anon 30 MB, peak
  56–66 MB, ΣVmHWM 306–331 MB; jemalloc middle — anon 65–75 MB, peak 92–110 MB;
  mimalloc highest — anon 89 MB, peak 113–115 MB, ΣVmHWM 465 MB. mallocng is
  frugal *because* it hands memory back — the same behaviour that costs the faults.
- Recommendation: **jemalloc for predictability**; mimalloc v3.5.4 release when
  the best case matters and the spread is acceptable.
- Packaging: `apk add jemalloc` + `LD_PRELOAD=/usr/lib/libjemalloc.so.2`
  (`/etc/conf.d/freeunit` or a Dockerfile `ENV`). Linking needs
  `--ld-opt="-Wl,--no-as-needed,-ljemalloc,--as-needed"` (a plain `-ljemalloc`
  is dropped silently by `--as-needed`). Alpine 3.24 ships jemalloc 5.3.0-r6.

### Fix 6 — reported

php/php-src#24308: `PHP_RSHUTDOWN_FUNCTION(syslog)` calls `php_closelog()`
unconditionally while `PG(have_called_openlog)` already tracks the state, so a
worker opens a new `connect("/dev/log")` per request when `error_log = syslog`.

### Fix 7 — closed, musl's own call

The extra `fcntl(F_SETFD, FD_CLOEXEC)` is **musl's**, not PHP's: `src/fcntl/open.c`
repeats it after `__sys_open_cp` when `O_CLOEXEC` is passed (identical in v1.2.5
and v1.2.6); `syscall.h` already passes the caller's flags to `openat`, so the
kernel sets the flag atomically and the `fcntl` repeats it. Measured in a fresh
`alpine:3.22`: C `open(O_CLOEXEC)` = 1 `fcntl`, without `O_CLOEXEC` = 0, glibc =
0; PHP CLI on Alpine gives 7 / 8 / 57 for 0 / 1 / 50 userland `fopen`s. Cost
~0.8 µs each, 2–4/req — far below the gap, and deliberate in both releases →
nothing to report.

## Corrected cause of the Drupal gap

Every `mmap` in the PHP worker comes from **libsqlite3** (which `pdo_sqlite`
opens and closes on each request), **not** from PHP or FreeUnit. This corrects
the first text of the issue, where the source of the large maps was open. The
**12–17% headline still holds** for the Drupal workload after fixes 1 and 2.

**Static files (new, the biggest real-site cost):** a 200 KiB file costs 158.6 µs
on Alpine, 125.4 µs on Debian and 77.2 µs on Alpine with jemalloc — 1.85 `mmap`
per response. glibc pays most of that cost too.

**Read-buffer churn correction:** the 16 KiB port-buffer churn comes only from
response parts of **15 bytes or less**; the 5-byte `hello` is close to the worst
case and a larger response part does not repeat it.

## Split for the release window

- **1.37.1 (landed):** fixes 1 and 2. The 1.37.1-slice items go in only if each
  is green by 2026-10-24: copy small response parts (≤256 bytes) into the request
  pool; an opt-in per-thread cache slot for the request object.
- **1.38:** reuse of static-file and body buffers; the PHP script-open change is
  **not** a patch change (it moves `open_basedir` and the directory answers); a
  `./configure --malloc=` option; the remaining sanitizer hardening.
- **Outside the repo:** the Alpine package change to jemalloc, and a short note
  for Alpine operators on the installation page. Not planned: a FreeUnit-owned
  `malloc` replacement.

## Not verified

Drupal on MySQL or PostgreSQL; the PHP worker with other language modules;
whether fixes 3/4 reach their estimated ~4 µs each on arm64 (only the call counts
are measured); behaviour past 10 minutes. The arm64 and amd64 hosts were shared
with other benchmarks at times; overlapping cells were repeated.

## Related

- `engineering/syscall-audit-kernel-requirements.md`
- `engineering/cgroup-v2-isolation-performance-brief.md`
- `engineering/fork-spawn-drupal-measurement.md`
