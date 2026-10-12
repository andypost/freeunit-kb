# Oracle Cloud stand — metrics and native ARM builds (plan)

Status: plan, written 2026-10-11 while the owner finishes the instance. Nothing has
been measured on it yet. The local host is a 512 MB container: heavy reads, builds
and experiments belong on a stand, and this is that stand.

## What the stand is for

1. **Metrics of this install** — cron job outcomes and durations, agent activity,
   and the numbers the quantization design needs.
2. **Native ARM build and test measurement** — aarch64 first, and the armv7 question
   answered by evidence rather than assumption.
3. **A place to break things** — fuzzing, sanitizer runs, and the 32-bit warnings
   build that no current CI job covers.

## Step 1: the armv7 probe, before anything is built

Oracle's ARM shape is Ampere A1, which is aarch64 (ARMv8-A, 64-bit). "armv7" is a
32-bit architecture, and whether an A1 instance can execute 32-bit ARM binaries
(AArch32 at EL0) is a property of the silicon and the kernel, not a configuration
choice. It is also **not yet verified for this platform** — do not plan around it,
and do not assume it either way.

The probe, about five minutes:

```sh
uname -m                      # expect aarch64
dpkg --add-architecture armhf && apt-get update
apt-get install -y libc6:armhf busybox-static:armhf   # or any tiny armhf binary
busybox               # 32-bit ARM binary: runs, or fails with Exec format error
```

- Runs → armv7 userland is possible on this host, and the 32-bit build path can be
  measured here (still AArch32 instructions on ARMv8 silicon, which is worth stating
  in any published number).
- Fails with `Exec format error` → armv7 needs different hardware (Raspberry Pi,
  ODROID, an older ARM cloud shape). The 32-bit leg then stays with cross-compilation
  and emulation, and the honest published statement is "aarch64 measured natively;
  armv7 covered by cross-build and emulation only".

Related, and tracked separately: #632 (no CI job compiles for a 32-bit target). A
green 32-bit build on this stand is the evidence that gate is missing.

## Step 2: native aarch64 measurement

Same command set on both architectures, recorded per run:

| Metric | Command | Why |
|---|---|---|
| Build wall clock | `./configure --hardening=strict --tests` then `make -j$(nproc)` | arch-dependent cost of the toolchain and the build |
| Warning count | grep the build log for `warning:` | strict build must be clean; a new warning is a finding |
| Peak RSS of the build | `/usr/bin/time -v make -j$(nproc)` | the A1 has 24 GB, a CI runner does not — catches memory-hungry steps |
| Test wall clock and result | `make test` | per-arch test time and failures |
| Binary facts | `file unitd`, `readelf -h`, binary size | 64-bit class, size delta against x86_64 |
| PHP stand, if installed | the php8.4-dev + libphp8.4-embed stand procedure | the SAPI path on aarch64 |

Two rules that make the numbers worth publishing:

- **Repeat three times and report the spread**, not one number: a shared cloud vCPU
  has steal time, and a single run invites a wrong conclusion.
- **Compare architectures, not code versions.** An aarch64 run against an x86_64 run
  measures the platform; a claim about a change needs both runs on the same host.

## Step 3: metrics for this install

Collection reads state that already exists — no new instrumentation in the agent:

| Metric | Source | Note |
|---|---|---|
| Cron runs, exit status, duration | `/opt/data/cron/jobs.json` plus the job state files | per job id, then per job name |
| Output produced per run | the cron output files' size | a proxy for "did the job have anything to say" |
| Delivery success | cron delivery records | a job that computes but cannot deliver is a silent failure |
| Webhook events by type and class | gateway log lines | counts only, never payloads |
| Turns per quantum, coalescing ratio | the quantization design's record | this is what says whether batching pays |
| Cost per job and per quantum | provider usage | needs the model's token accounting |

Rules: counts and timings only — **no payloads, no message bodies, no tokens, no
personal data**. The stand collects, the bot host stays light. Transport is either a
push from a small script or a pull over SSH; decide when the host has a name.

## Step 4: what the owner needs to provide

- SSH access (user, key, address) once the instance is up.
- Shape and OS: A1 OCPU/memory, and the image (Ubuntu or Debian) so the package
  commands above are right.
- Permission to install build dependencies (openssl, brotli, zstd, pcre2, php8.4-dev,
  libphp8.4-embed) and to run `make test`.
- A decision on whether the stand may hold the 32-bit warning build (it is slow under
  emulation, fast if step 1 says AArch32 works).

## Do not claim

- No cross-architecture performance comparison from a single run.
- No "armv7 measured natively" until the step-1 probe passes on the stand.
- No metric that includes message content or a credential.

## Related

- `engineering/webhook-reaction-quantization.md` — the design that defines the
  quantum metrics
- `engineering/tls-1.3-and-kubernetes.md` — priority work that also wants the ARM
  stand for its test legs
- `strategy/unit-work-process.md` — where stand work sits in the stream rules
