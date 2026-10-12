# Scaleway Benchmark Plan

## Why Scaleway

| Factor | Scaleway | Hetzner |
|--------|----------|---------|
| Billing | **Per minute** — exact | Per hour — round up |
| Instance for 30 min bench | ~€0.03 | €0.30–2.50 |
| CPU | AMD EPYC Milan, Ampere Altra (native ARM) | Intel Xeon (older gen) |
| Network | 10 Gbps | 1–10 Gbps |

## Instance types for benchmarks

| Instance | vCPU | RAM | SSD | Price/h | 30 min cost | Best for |
|----------|------|-----|-----|---------|------------|----------|
| **DEV1-L** | 4 | 4GB | 20GB | ~€0.06 | ~€0.03 | PHP benchmarks, low conn |
| **DEV1-XL** | 8 | 8GB | 40GB | ~€0.12 | ~€0.06 | C10K, 10k connections |
| **GP1-S** | 2 | 4GB | — | ~€0.12 | ~€0.06 | Compare with current Hetzner |
| **GP1-M** | 4 | 8GB | — | ~€0.24 | ~€0.12 | Drupal real-world bench |

**Recommended:** DEV1-XL (8 vCPU, 8GB) for serious C10K benchmarks — enough CPU for both the server AND the load generator (wrk/oha) on the same host.

## Benchmark Scenarios

### Scenario 1: Low concurrency (128 conn, 10s)

```bash
oha -n 100000 -c 128 --latency-correction \
  http://localhost:8080/small-fixed-response.data
```

Goal: confirm baseline, compare against earlier 128-conn results:
- Buran: ~198K RPS
- FreeUnit: ~188K RPS
- nginx+FPM: ~57K RPS

### Scenario 2: C10K (10,000 conn, 30s)

```bash
oha -n 500000 -c 10000 --latency-correction \
  http://localhost:8080/php-test.php
```

Goal: compare against earlier results:
- Buran: ~265K RPS
- FreeUnit: ~141K RPS
- nginx+FPM: ~13K RPS

### Scenario 3: FreeUnit vs Buran (fresh data)

Run BOTH on same instance type, same kernel, same PHP version.

### Scenario 4: ARM64 (Ampere Altra)

Create equivalent ARM64 instance, re-run scenarios 1-2.
Check if ARM performance gap exists.

## Benchmark toolkit

```bash
# Tools to install on instance (boot script):
apt install -y git make gcc pkg-config \
  libpcre2-dev libssl-dev libxml2-dev \
  php8.5-dev php8.5-cli php8.5-common \
  libphp-embed  

# Load generators:
curl -LO https://github.com/hatoo/oha/releases/latest/download/oha-linux-amd64
chmod +x oha-linux-amd64
```

## Cost

| Scenario | Instance | Time | Cost |
|----------|----------|------|------|
| 128 conn, 3 stacks | DEV1-XL | 30 min | €0.06 |
| C10K, 3 stacks | DEV1-XL | 30 min | €0.06 |
| ARM64, same 2 | ARM64-DEV1-XL | 30 min | €0.06 |
| Setup + teardown | — | 30 min | €0.06 |
| **Total** | | **2 hours** | **~€0.24** |

€0.24 за полную сессию бенчмарков — и знаешь точные цифры на свежем железе.

## Execution (one command bootstrap)

```bash
# 1. Create instance via CLI
scw instance server create type=DEV1-XL \
  zone=fr-par-1 image=debian-trixie

# 2. Boot script does:
#   - apt install build deps
#   - clone freeunit + buran
#   - build both
#   - generate test content
#   - run oha benchmarks in sequence
#   - print results as table

# 3. Instance auto-terminates after bench
#   - ...or manually: scw instance server terminate
```

## Config template for FreeUnit benchmark

Create `bench-config.json`:

```json
{
  "listeners": {
    "*:8080": { "pass": "applications/bench" }
  },
  "applications": {
    "bench": {
      "type": "php",
      "root": "/var/bench/web",
      "script": "index.php",
      "processes": { "max": 8 }
    }
  }
}
```

Simple test PHP:

```php
<?php
echo "ok";
```

And a small static file for baseline.
