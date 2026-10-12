# Existing Laravel Benchmarks — Study Before Proposing New Ones

**Added:** 2026-07-20
**Context:** FreeUnit P4 positioning for Laravel ecosystem
**Principle:** Don't reinvent the benchmark wheel — study what exists first.

## Known benchmark repositories and resources

### Official and community repos

| Source | What it covers | URL |
|--------|---------------|-----|
| **Laravel Octane** | Official Octane benchmarks, includes comparison helpers for Swoole and RoadRunner backends | github:laravel/octane |
| **PHP Benchmarks** | Cross-server comparison (nginx+fpm, RoadRunner, Swoole, FrankenPHP) | github:php-benchmarks |
| **PHP-FPM vs Swoole vs RoadRunner** | Community-driven throughput/latency comparisons | Public blog posts (multiple authors) |
| **FrankenPHP benchmarks** | Official FrankenPHP vs Caddy+FPM, RoadRunner comparisons | github:dunglas/frankenphp |
| **TechEmpower Framework Benchmarks** | Industry-standard cross-language benchmarks (PHP framework round) | techempower.com/benchmarks |
| **roadrunner-bench** | RoadRunner-specific benchmark scenarios | github:roadrunner-server |

### What to look for

1. **Their methodology** — concurrency levels, keepalive vs close, warmup, noise floor
2. **Their app model** — hello-world vs real Laravel app? How many service providers?
3. **Their metrics** — RPS only? P50/P99? CPU µs/req? Memory?
4. **Their environment** — CPU, RAM, kernel, PHP version, opcache settings

## Why this matters

Before FreeUnit designs its own Laravel benchmark suite, the team must:
1. Review existing repos for methodology flaws to avoid repeating them
2. Understand which scenarios already have solid data
3. Decide whether a new benchmark suite adds value or just duplicates effort
4. If new benchmarks are needed, design them to fill gaps (e.g. io_uring vs epoll for Laravel, datagram dispatch, persistent worker memory stability under Laravel load)

## Recommendation

- Check the `octane-roadrunner-frankenphp-research.md` doc first (already in KB)
- Scan GitHub for any Laravel benchmark repo with reproducible CI pipeline
- If proposing a new FreeUnit Laravel benchmark, explain what gap it fills that existing benchmarks don't cover
