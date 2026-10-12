# Rapira (rapira.rs) — competitor notes (FreeUnit landscape)

**Created:** 2026-09-23 by SOUL. Sources: rapira.rs (home, /docs/intro,
/docs/process-model, /docs/execution-modes, /docs/http, /blog), README of
github.com/rapira-rs/rapira, GitHub org API (public, unauthenticated).

## What it is

- PHP application server written in **Rust**, MIT, public since 2026-07-26.
- **By the RoadRunner maintainers** — the Go/RoadRunner line continued, but
  restarted as: Rust + **embedded PHP interpreter** (custom SAPI, Zend in the
  server process). No FastCGI between server and PHP; no PHP-CLI workers and
  no Goridge JSON IPC in-process (Goridge/FastCGI/C ABI appear only as
  extension surfaces in the SDK story).
- Org `rapira-rs`: main repo `rapira` (Rust, 39★ on 2026-09-23, described as
  "SAPI core API used to integrate with PHP SAPI and provide API for
  plugins"), plus `rapira-windows` (ZTS build), `sdk-php`, `http-php`
  (PSR-7 server-request factories per mode), `testing-php` (live-server test
  harness), `contract`, `symfony`, docs repo. Sponsor: Buhta (buhta.com).
- Builds: Linux + macOS, separate payloads for PHP 8.4 and 8.5, each with its
  own libphp; PHP 8.4 ships `opcache.so` beside libphp, 8.5 has OPcache inside
  libphp. Docker `ghcr.io/rapira-rs/rapira:php8.5`. Config = `rapira.toml`.

## Process model (remarkably close to FreeUnit's shape)

- One **master** + worker pool. Master: binds listen socket(s), starts PHP
  **once** (MINIT in the single-threaded master → OPcache creates its SHM
  segment), then forks workers; every child inherits socket + initialized
  engine + the same OPcache segment (one worker compiles, others reuse).
- Each worker = one NTS interpreter + async HTTP server (**hyper** on a private
  tokio runtime, two threads), calls `accept()` on the inherited socket; the OS
  distributes connections. Master serves nothing, `poll(2)` on a self-pipe,
  ~1 s maintenance, optional `ondemand` accept.
- Requests never cross a process boundary. Same pool creation/supervision/
  reloads in all three modes; only `pool.mode` changes in-worker handling.

## Execution modes (`pool.mode` / `Rapira\Mode`)

- **Classic** — request per PHP request, as under php-fpm ("a current
  application can run without code changes when Rapira replaces php-fpm").
- **Worker** — script initialized once, loop handles requests, superglobals
  refilled per request; static state persists.
- **Dispatcher** — script gets request objects through an API call, can
  process sequentially or **concurrently with fibers**; superglobals not used.

## HTTP side

- Own HTTP/1.1 + HTTP/1.0 server on hyper; parses requests itself, no
  proxying to another server; middleware can answer before PHP (static files).
- **No TLS** — expects a TLS-terminating proxy in front. CONNECT → 501.
  `http.keepalive_timeout_secs` default 60 → 408 then close.
- Careful CGI mapping (`$_SERVER`, absolute-form targets, authority vs Host).

## Positioning vs our landscape

- **Slot = same as FrankenPHP** (embedded SAPI + persistent worker mode), and
  **supersedes RoadRunner's** design (RoadRunner: Go server + PHP-CLI workers +
  JSON-over-pipes IPC + TLS/HTTP2 built in). Rapira trades those for embedded
  Zend and no TLS.
- **Direct neighbour of FreeUnit**: PHP app server, master/worker with shared
  listen socket, interpreter inside the server process, own HTTP server, TLS
  left to a proxy, php-fpm drop-in for the classic path. Differences: Rust
  (vs C), TOML config + `rapira.toml` (vs nginx-derived config), hyper/tokio
  (vs our event loop), no TLS/HTTP2/3 yet, HTTP-only feature set, young
  (~39★, no plugin parity — "plans to support more RoadRunner plugin
  functions"), Linux/macOS only (Windows via a separate ZTS build).
- **Its compatibility trick is protocol-level, not engine-level:** Rapira does
  NOT imitate PHP's engine — it hosts the real Zend. It imitates **php-fpm's
  deployment contract** (classic mode = drop-in). FreeUnit's analogue is
  nginx-config/drop-in compatibility.
- The same split appears across this space: one design owns the
  accept/queue/protocol path and embeds the engine in process, another is a
  FastCGI drop-in for php-fpm. The direction of imitation differs — some
  replace the engine and skin PHP, Rapira keeps the engine and imitates the
  server.

## Watch items

- Plugin parity with RoadRunner (queues, metrics, gRPC, hot reload).
- If HTTP/2, TLS, or an in-process engine embedding path appears, Rapira
  becomes the closest structural rival to FreeUnit.
- Ext-php-rs/Zend embedding is the same technical ground as FreeUnit's
  in-process OPcache/fork work — worth diffing their SAPI choices.
