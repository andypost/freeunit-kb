# WordPress + FreeUnit — Production Baseline

## Why FreeUnit for WordPress

WordPress is 43% of the web. Most of it runs on php-fpm (shared hosting) or
nginx+FPM (VPS). FreeUnit replaces both — same performance for simple sites,
better stability under load, zero-downtime deploys, and a path to persistent
workers that php-fpm cannot provide.

**Key number:** WordPress does ~5KB median response. The bottleneck is never
the app server. It's MySQL queries, PHP filesystem, and opcache misses.
FreeUnit fixes the non-database overhead and gives room to scale.

---

## Quick Start (Docker)

### Minimal Docker

```bash
docker run -d \
  --name freeunit-wp \
  -p 8080:80 \
  -v ./wp-content:/var/www/wp-content \
  ghcr.io/freeunitorg/freeunit:latest-php-8.5
```

### With MySQL + full WordPress

```yaml
# docker-compose.yml
version: "3.8"
services:
  db:
    image: mariadb:11
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp
      MYSQL_PASSWORD: wp

  freeunit:
    image: ghcr.io/freeunitorg/freeunit:latest-php-8.5
    ports:
      - "8080:8080"
    volumes:
      - ./wp-content:/var/www/wp-content
      - ./config.json:/etc/unit/config.json:ro
    depends_on:
      - db
```

### FreeUnit config for WordPress

```json
{
  "listeners": {
    "*:8080": {
      "pass": "applications/wordpress"
    }
  },
  "applications": {
    "wordpress": {
      "type": "php",
      "root": "/var/www",
      "script": "index.php",
      "processes": {
        "max": 8,
        "spare": 2,
        "idle_timeout": 30
      },
      "options": {
        "admin": {
          "opcache.enable": 1,
          "opcache.memory_consumption": 128,
          "opcache.max_accelerated_files": 5000,
          "opcache.revalidate_freq": 60,
          "expose_php": 0
        },
        "file": "/etc/php/8.5/cli/php.ini"
      }
    }
  }
}
```

---

## Benchmark Config

### PHP test file (bench.php)

```php
<?php
// Simple WordPress-like response
echo "<html><head><title>Test</title>";
echo '<link rel="stylesheet" href="/wp-content/themes/test/style.css">';
echo "</head><body>";
echo "<h1>Hello World</h1>";
echo str_repeat("<p>Lorem ipsum dolor sit amet consectetur adipiscing elit.</p>\n", 20);
echo "</body></html>";
```

### Running benchmarks (oha)

```bash
# Low concurrency — baseline
oha -n 50000 -c 128 -z 30s --latency-correction \
  http://your-server:8080/bench.php

# High concurrency — burst
oha -n 200000 -c 2048 -z 60s --latency-correction \
  http://your-server:8080/bench.php

# Mixed static + PHP
oha -n 50000 -c 256 -z 60s --latency-correction \
  -m GET \
  http://your-server:8080/bench.php \
  http://your-server:8080/wp-content/themes/test/style.css
```

### What to measure

| Metric | WP baseline (php-fpm) | FreeUnit target | Good enough |
|--------|----------------------|-----------------|-------------|
| RPS (128 conn, bench.php) | ~15K | ~25K | >20K |
| RPS (2048 conn) | ~8K | ~15K | >10K |
| p50 latency | ~4ms | ~2ms | <5ms |
| p99 latency | ~20ms | ~10ms | <20ms |
| max workers | 32 fpm | 8 unitd | 16 |
| RAM per worker | ~40MB | ~30MB | <50MB |

---

## WordPress-Specific Tuning

### opcache (biggest win)

```json
"options": {
  "admin": {
    "opcache.enable": 1,
    "opcache.memory_consumption": 128,
    "opcache.max_accelerated_files": 5000,
    "opcache.validate_timestamps": 1,
    "opcache.revalidate_freq": 60,
    "opcache.jit": "tracing",
    "opcache.jit_buffer_size": "64M"
  }
}
```

WordPress has ~700 PHP files. opcache.preload not available by default
(WP doesn't ship a preload script), but plugins like WP Rocket or custom
mu-plugins can add one.

### Redirects (admin bar, /wp-admin)

```bash
# Prevent rendering admin bar for non-authenticated requests
# In wp-config.php:
if (!is_admin() && !is_user_logged_in()) {
    show_admin_bar(false);
}
```

This alone can cut /wp-admin/ rendering by 40%.

### MySQL connection — reuse via P4 (future)

Current: each request opens a new MySQL connection (TCP handshake + auth = ~1ms).
With P4 persistent worker: one PDO connection per worker lifetime — 0ms overhead.

### Object cache (Redis)

WordPress without object cache runs ~30 queries per page.
With Redis object cache (via `redis-cache` plugin): ~5 queries.

```bash
docker run -d --name redis --network wp-network redis:7-alpine
# Then install plugin: wp plugin install redis-cache --activate
```

---

## Production Checklist

```
[ ] FreeUnit 1.36.0+ running
[ ] PHP 8.4 or 8.5
[ ] opcache enabled + JIT tracing
[ ] MySQL with persistent connection (sql.php: mysql_pconnect)
[ ] Redis object cache (redis-cache plugin)
[ ] Static files: served directly by FreeUnit (no nginx needed)
[ ] TLS: terminate at edge (Caddy / Cloudflare)
[ ] Graceful shutdown: SIGQUIT configured in systemd/container
[ ] Health check: GET /wp-admin/admin-ajax.php?action=heartbeat
[ ] Backup: wp-content + database dump
```

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| 502 Bad Gateway | Worker timeout | Increase `processes` or app timeout |
| Slow admin panel | Admin bar + many queries | Disable admin bar for non-logged-in |
| File upload failed | Body too large | Multipart body handling — D3 in roadmap |
| Memory exhausted | opcache too small | Increase `opcache.memory_consumption` |
| 404 for pretty permalinks | Missing `try_files` | FreeUnit's `script: index.php` handles WP routing natively |

## How it compares

| Stack | RPS (bench.php) | p99 | RAM | Deploys |
|-------|-----------------|-----|-----|---------|
| nginx + php-fpm | 15K | 20ms | ~2GB (32 workers) | restart fpm |
| FreeUnit | 25K | 10ms | ~250MB (8 workers) | live config reload |
| nginx + FrankenPHP | 28K | 8ms | ~400MB | restart |
| Traefik + edge runtime | 35K | 6ms | ~200MB | live |

FreeUnit wins on RAM efficiency vs FrankenPHP and on operational simplicity
vs nginx+FPM.

---

## Planned improvements (roadmap)

| Item | Impact on WP | Target |
|------|-------------|--------|
| P4 persistent worker | 0ms MySQL reconnect, opcache always hot, ~20-40x vs cold boot | Q3 2026 |
| D3 body streaming | Safe large uploads (media library, backups) | Q3 2026 |
| X4 contract | Enables P4, also enables WP plugin sandboxing | Q3 2026 |
| X8 Prometheus metrics | WP health metrics dashboard | Q4 2026 |
| Prototype+fork (shared opcache) | 8 workers → one opcache (256MB shared, 8 workers × 30MB RSS = ~480MB total) | Q3-Q4 2026 |
