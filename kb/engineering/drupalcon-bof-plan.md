# DrupalCon BoF Plan: FreeUnit + Buran for Drupal Development

> **ASPIRATIONAL / SUPERSEDED — 2026-09-17.** This document was written as a
> scenario, not from the product: the `freeunit` CLI, the YAML config and the
> `freeunit worktree` workflow described below **do not exist**. The real
> surface is the JSON config API (`PUT /config`), `unitctl` and Docker images.
> Do not quote this document in public copy or on stage. The event is
> **DrupalCon Rotterdam, 28 Sep – 1 Oct 2026**, and the current, grounded
> promotion plan is `strategy/drupalcon-rotterdam-2026-promotion-plan.md`.

**Target:** DrupalCon Europe, September 2026 (BoF session, ~45 min)
**Speaker:** Andrey Postnikov (@andypost)
**Audience:** Drupal developers, devops, agency leads
**Goal:** Show that FreeUnit + Buran solve real Drupal dev pain points

---

## Session Title (options)

1. **"Kill DDEV, keep Drupal: FreeUnit + Buran for local dev and prod"**
2. **"Drupal on Buran: 3x faster local dev with dynamic worktrees"**
3. **"From Lando to FreeUnit: persistent workers, zero-config PHP, and why your local should match prod"**

---

## Narrative Arc (45 min)

### Part 1: The Problem (5 min)

**"Every Drupal agency has this setup:"**
```
Developer laptop → Docker (DDEV/Lando) → nginx + PHP-FPM + MySQL + Redis
```

**Pain points:**
- Slow startup: `ddev start` = 30-60s, cold PHP on every restart
- Memory overhead: Docker VM + nginx + FPM + MySQL containers = 2-4GB RAM
- Prod ≠ local: nginx config differs, FPM tuning differs, paths differ
- Branch switching: `git checkout` → opcache stale → white screen → cache rebuild
- No H2/H3 locally: `curl --http2` fails, Service Worker testing broken
- Multisite: each site needs separate container, separate ports

**Punchline:** "What if I told you FreeUnit boots Drupal in 0.3s, uses 50MB RAM,
and your local config IS your prod config?"

### Part 2: FreeUnit for Local Dev (10 min)

**Demo: cold start**
```bash
# Install FreeUnit (one binary, no Docker)
brew install freeunit  # (or apt, or just download)

# Configure Drupal site
cat > freeunit.yaml << 'EOF'
listeners:
  "*:8080": { route: drupal }
routes:
  drupal:
    - match: "/sites/default/files/*"
      action: { share: "/var/www/drupal$uri" }
    - action: { application: drupal }
applications:
  drupal:
    module: php
    processes: 2
    working_directory: /var/www/drupal/web
    settings:
      document_root: "web"
      index: "index.php"
      root:
        - "/web"
    targets:
      prepare:
        - composer install --no-dev --optimize-autoloader
EOF

# Start (instant)
freeunit start
# → "using epoll_edge event engine"
# → "worker[1] ready" "worker[2] ready"
# → First request: 0.3s (warm opcache after prepare)
```

**Key points:**
- No Docker needed — single binary, ~5MB
- PHP embedded via SAPI — no FPM overhead
- Persistent workers — opcache stays warm across requests
- `prepare` target runs `composer install` automatically
- Config is the same for local and prod (one YAML)

**Demo: branch switching with dynamic worktrees**
```bash
# Create worktree for feature branch
freeunit worktree add feature/issue-1234
# → FreeUnit creates git worktree, runs composer install
# → New worker pool on port 8081, separate opcache

# Now you have:
# Port 8080: main branch (warm, stable)
# Port 8081: feature/issue-1234 (warm, separate cache)

# Switch between them in browser, no cache rebuild needed
# Each worktree has its own:
#   - opcache (PHP file cache)
#   - Drupal cache (separate DB or DB prefix)
#   - Composer autoloader

# Remove when done
freeunit worktree remove feature/issue-1234
```

**This is the killer feature for Drupal dev.** No more:
- `drush cr` on every branch switch
- Docker container per branch
- "Wait, which branch am I on?" confusion
- Stale opcache white screens

### Part 3: Production Emulation (10 min)

**"Your local should BE your prod"**

```yaml
# freeunit.yaml — works on laptop AND production server
listeners:
  "*:8080":
    route: drupal

routes:
  drupal:
    # Static files (managed files, CSS/JS aggregates)
    - match: "/sites/default/files/(css|js)/"
      action:
        share: "/var/www/drupal/web$uri"
        # io_uring sendfile: zero-copy static serving
        response_headers:
          Cache-Control: "public, max-age=31536000, immutable"

    # Image styles (on-demand generation)
    - match: "/sites/default/files/styles/"
      action: { application: drupal }

    # PHP
    - action: { application: drupal }

applications:
  drupal:
    module: php
    processes:
      dynamic:
        max: 8
        spare: 2
        idle_timeout: 60
    working_directory: /var/www/drupal/web
    settings:
      document_root: "web"
      index: "index.php"
    targets:
      prepare:
        - composer install --no-dev --optimize-autoloader
    environment:
      DATABASE_URL: "${DATABASE_URL}"
      DRUPAL_HASH_SALT: "${DRUPAL_HASH_SALT}"
      SYMFONY_DEBUG: "${DEBUG:-false}"
```

**Demo: graceful reload (zero-downtime deploy)**
```bash
# Deploy new code
git pull origin main
composer install --no-dev

# Reload workers gracefully
freeunit reload
# → New workers spawn with new code + fresh opcache
# → Old workers finish in-flight requests
# → Zero 502s, zero dropped connections
# → Total downtime: 0ms
```

**vs Drupal traditional deploy:**
```bash
# Traditional
drush state:set system.maintenance_mode 1
git pull
composer install
drush updb
drush cr
drush state:set system.maintenance_mode 0
# → 30-60s downtime, users get maintenance page
```

### Part 4: Buran Integration (10 min)

**"FreeUnit is great for PHP. Buran is great for the edge."**

```
Internet → Buran (H2/H3/TLS) → BWP → FreeUnit (PHP workers)
```

**Architecture:**
```yaml
# buran.yaml (edge/frontend)
listeners:
  "*:443":
    route: main
    tls:
      cert: /etc/ssl/drupal.crt
      key: /etc/ssl/drupal.key
      alpn: ["h2", "http/1.1"]

routes:
  main:
    - action: { application: freeunit }

applications:
  freeunit:
    module: php
    processes: { dynamic: { max: 16, spare: 4 } }
    # Buran spawns FreeUnit PHP workers directly via BWP
```

**Why this matters for Drupal:**

1. **HTTP/2 + HTTP/3** — finally supported for Drupal, no nginx required
2. **BWP kernel dispatch** — under traffic spikes (Habr article, Black Friday):
   - nginx+FPM: FPM pool exhausted → 502 → visitors see error
   - Buran: kernel dispatches to idle worker → all visitors served
3. **Static assets** — Buran serves CSS/JS/images directly (zero-copy),
   PHP workers never touch static files
4. **WebSocket** — BWP supports WS upgrade: Drupal real-time notifications,
   LiveChat, collaborative editing

**Demo: live benchmark (if venue wifi allows)**

```
# Show the C10K benchmark side by side:
# nginx+FPM: 13k RPS, 3% errors, p99=1258ms
# Buran: 265k RPS, 0% errors, p99=154ms
```

### Part 5: Roadmap & Call to Action (10 min)

**"What's coming and how to get involved"**

**Near-term (Q3 2026):**
- io_uring RECV tier (zero-copy recv) — better static + upload
- BWP listener in FreeUnit (kernel-arbitrated dispatch)
- Drupal-optimized defaults (worktree, multisite support)

**Medium-term (Q4 2026 - Q1 2027):**
- MySQL connection pooling in SAPI
- Redis cache bridge (embedded)
- HTTP/2 via Buran frontend
- opcache.preload automation

**"Drupal community: what we need from you"**
- Test FreeUnit on real Drupal sites (complex contrib setups)
- Report multisite edge cases
- Help design the `freeunit worktree` UX for Drupal
- Contribute Drupal-specific CI tests

---

## Demo Checklist (prepare before BoF)

- [ ] Laptop with FreeUnit + Drupal 11 installed and warm
- [ ] Buran binary compiled and configured
- [] Benchmark slides/screenshots (venue wifi may not allow live)
- [ ] `wrk` benchmark scripts ready
- [ ] Two git worktrees prepared (main + feature branch)
- [ ] Backup video of all demos (in case of projector/wifi failure)

---

## Key Talking Points (cheat sheet)

| Question | Answer |
|----------|--------|
| "Is this DDEV replacement?" | Yes, for PHP. MySQL/Redis still need containers or native install. |
| "Does it support multisite?" | Yes — each site = separate route in config. Planned: auto-detect. |
| "HTTP/2?" | Not in FreeUnit core. Use Buran frontend or any reverse proxy. |
| "How is this different from FrankenPHP?" | FrankenPHP = Go wrapper around PHP. FreeUnit = C-core app server with persistent workers, io_uring, kernel dispatch. |
| "Production ready?" | FreeUnit v1.35.6 in August. Buran — ask project author. |
| "Windows/Mac?" | FreeUnit = Linux native (WSL2 on Windows, Docker on Mac). Buran = Linux. |
| "License?" | Apache 2.0 (FreeUnit). Check Buran. |

---

## Q&A Prep

**Q: "How does this compare to RoadRunner?"**
A: RoadRunner is Go-based, uses Golang for the supervisor and PHP workers via
FastCGI-like protocol. FreeUnit is C-core with embedded PHP SAPI — no separate
language, no FastCGI overhead. RoadRunner can't do kernel-arbitrated dispatch.

**Q: "Why not just use nginx + FPM?"**
A: Show the C10K slide. nginx+FPM: 13k RPS, 3% errors, p99=1258ms. FreeUnit:
141k RPS, 0% errors, p99=102ms. Under load, FPM queuing kills user experience.

**Q: "Does FreeUnit work with X debug?"**
A: Yes — xdebug works as usual in embedded SAPI. Configure via php.ini.

**Q: "Database?"**
A: FreeUnit is PHP application server, not database. Use MySQL/PostgreSQL as
usual. Future: embedded connection pooling.

---

## Post-BoF: Follow-up materials

- GitHub issue template for Drupal-specific bug reports
- `freeunit-drupal` starter repo (freeunit.yaml + composer.json template)
- Blog post: "Drupal on FreeUnit: benchmark vs DDEV"
- Video: "FreeUnit worktree workflow for Drupal development"
