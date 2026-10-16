# Isolation research brief — cgroup v2 consequences and performance (2026-10-11)

**Status: HOLD.** Started only after the **1.37.1 tag exists** (Andrey's sequencing:
"сначала закончим 1.37.1"). Recorded here and as an issue in `freeunitorg/freeunit-exp`
so the hold has a gate instead of being re-asked. **Task filed 2026-10-11:
`freeunitorg/freeunit-exp#22`** ("Agent task: isolation + cgroup v2 — what Unit places,
what the operator must limit, and what it costs", label `agent`, author
`freeunit-agent[bot]`). Everything below is verified
against `origin/master` on 2026-10-11 (master `0f1ec0b1`-era tree, 96 commits past
`1.37.0`).

## 1. Verified current state (this is the delta the research starts from)

- **The config surface is placement only.** `isolation.cgroup` accepts exactly one
  member, `path` (required, validated by `nxt_conf_vldt_cgroup_path` —
  `src/nxt_conf_validation.c:1578`). Nothing writes a limit file: there is no
  `memory.max`, `memory.limit_in_bytes`, `cpu.max` writer, no `cpu.cfs_*`, no
  `subtree_control` write anywhere in `src/`. Unit creates the leaf directory and
  appends `/cgroup.procs` (`src/nxt_cgroup.c`), nothing more. Upstream's own 1.29.0
  notes say the same: "we support the cgroup V2 API to provide the ability to place
  each application into its own cgroup".
- **Consequence to document and test:** limits are the operator's job (systemd slice,
  Docker, or hand-written cgroupfs). On a v2 host a leaf whose parent has not enabled
  the controller in `cgroup.subtree_control` has **no limit files at all** — limits
  then read as "unlimited" and nothing fails loudly. That silent-no-op path is the
  first thing to prove or disprove.
- **CPU-limit awareness exists, and only for the router thread count.** `nxt_cgroup_cpu_limit()`
  scans `/proc/self/mountinfo` + `/proc/self/cgroup`, walks up reading `cpu.max`
  (`nxt_cgroup_cpu_max_parse()`, `src/nxt_lib.c`), and lowers `nxt_ncpu`; the original
  value stays in `nxt_ncpu_unlimited` and the record goes to `unit.log`. It is
  computed **once at startup**.
  Work already merged: #548 (lower CPU count to the cgroup v2 limit), #547 (router
  threads follow it), #576 (log record + cgroup walk tests), #515 (unshare the cgroup
  namespace after the move). **Open: #659** — `nxt_cgroup_mountinfo_find()`, keep
  scanning past unrelated cgroup2 mounts (first mount whose root contains the cgroup;
  Go and Rust std make the same choice). Tests exist: `src/test/nxt_cpu_limit_test.c`
  (9 mountinfo fixtures), `src/test/nxt_cgroup_test.c`.
- **Isolation itself is unshare-after-fork + mount/rootfs**, and needs `mount`,
  `umount2`, `pivot_root`, `unshare`, `openat2`, i.e. CAP_SYS_ADMIN and a permissive
  seccomp/AppArmor policy — the decided seccomp/Docker work
  (`engineering/seccomp-isolation-plan-summary.md`) covers the *syscall-policy* half
  and is a separate track from cgroup semantics. Do not re-open it here.
- Per-process cgroup move reads `/proc/<child>/cgroup` (not `/proc/self/cgroup`)
  because the parent may have moved; cleanup walks up to the parent's own cgroup and
  stops at `NXT_CGROUP_ROOT`.

## 2. Research questions (each needs a live answer, not an opinion)

1. **Delegation on v2.** With `subtree_control` not carrying `+cpu +memory` in the
   parent: does Unit still create the leaf and move the app there, and do the limit
   files exist? What does `/status` and the app see?
2. **The "no internal processes" rule.** v2 forbids enabling a controller in a cgroup
   that has members. If the operator points `path` at a cgroup that already holds
   processes (unitd's own), what is the failure — `EBUSY`, `EPERM`, silent? Which
   paths are legal for a systemd-managed unitd (`Delegate=yes`, user service,
   `systemd --user`, Docker default cgroup parent)?
3. **Threaded subtrees.** If an ancestor is `cgroup.type=threaded`, `cgroup.procs`
   cannot be used (only `cgroup.threads`). Does the app move fail, and with what errno?
   Is that reachable in a default container runtime?
4. **Rootless.** On the rootless stand (user namespace, no root): can the main process
   create/have a cgroup path at all, and what does the CPU-limit walk read when
   `/sys/fs/cgroup` is the user's delegated subtree?
5. **v1/hybrid hosts.** `nxt_mk_cgpath()` parses `/proc/<pid>/cgroup`; v1 writes
   `<id>:<controllers>:<path>` and v2 `0::<path>`. Does the same config land in the
   right directory on a v1/hybrid host (EL), and is the CPU-limit walk a no-op there
   (it reads v2 `cpu.max` only)?
6. **Where the operator's own numbers come from.** Which documented recipe do we
   recommend per platform (systemd slice with `CPUQuota`/`MemoryMax`, Docker `--cpus`
  /`--memory`, hand-written `cpu.max`/`memory.max`), and what does Unit need to state
   so users stop expecting the config to set limits?

## 3. Performance measurements to produce (the second half of the ask)

Every number below gets method + version + caveat, per the standing rule.

- **ncpu derivation effect.** Many-core host, container limited to N CPUs: router
  thread count and RPS/p95/p99 with the limit honoured vs the pre-#548 behaviour
  (host ncpu). Does lowering thread count help or hurt short PHP requests? Which N
  is the crossover?
- **Throttling trace.** `cpu.stat` `nr_throttled` / `throttled_usec` for a PHP
  workload with router threads + N workers vs a quota set below them; show the stall
  pattern rather than asserting "limits are fine".
- **Restart-only semantics.** The limit is read once at startup: prove that raising
  the quota at runtime does not change the thread count until unitd restarts, and
  state it as a documented consequence.
- **Memory accounting under v2 with shared opcache.** `memory.max` is a cgroup
  aggregate; the fork/prototype work shares one opcache SHM across workers and children
  (measured already: worker 16.1 MB RSS, fork child +11 MB RSS / 3.4 MB PSS). Show what
  a per-app `memory.max` counts when N children share one SHM, and whether PSS-style
  accounting makes the limit plausible or traps users (v2 has no `memory.kmem`
  split, has `memory.high` throttling and `memory.swap.max` which v1 lacks).
- **OOM behaviour per app.** With `memory.oom.group` unset (default 0) v2 kills a
  single process; with it set, the whole cgroup. Which one does an over-limit PHP app
  get today, and does Unit's respawn loop turn an OOM into a loop worth alerting on?
- **CPU-limit vs worker count interaction.** If the quota is below the configured
  `processes.max`, the app is throttled rather than refused — measure and state the
  honest reading (the CPU limit does not cap concurrency for I/O-bound PHP, it caps
  time).

## 4. Deliverables of the research

1. A KB doc with the answers per question, each with the platform/version where it
   was proven (extend this file, dated sections).
2. Measurements from §3 with the harness named and reproducible.
3. For anything that is a code defect: an issue on `freeunitorg/freeunit` + a
   failing-first test, not a patch smuggled into an unrelated PR.
4. Documentation delta: the docs page must state that Unit **places** and the
   operator **limits**, with one recipe per platform.
5. For anything that is a content-grade fact: hand it to the content stream (X /
   LinkedIn) — that is the point of doing it on the `-exp` side.

## 5. Out of scope

- Re-opening the seccomp/Docker decision (`seccomp-isolation-plan-summary.md`).
- Control-API auth (D7) and TLS work.
- Anything touching the 1.37.1 train while it is open.

## 2b. Probe results — phase A (2026-10-11, live)

Stand: Scaleway DEV1-M, **Debian 13 Trixie, kernel 6.12.111+deb13-cloud-amd64, 3 vCPU**,
cgroup2 mounted `rw,nosuid,nodev,noexec,nsdelegate,memory_recursiveprot`. Raw log kept
with the session; every line below is a live observation, not a reading of the kernel docs.

1. **What systemd leaves enabled at the root:** `root subtree_control: cpu memory pids`
   (of `cpuset cpu io memory hugetlb pids rdma misc`) — i.e. only those three controllers
   exist for anything below `/`, on a stock Trixie install.
2. **Enabling controllers in an empty cgroup works**, and the children then really do get
   the limit files: after `+cpu +memory` on `e1`, its child carries `cpu.max`, `memory.max`,
   `memory.high`, `memory.swap.max`, `memory.oom.group`, `pids.max`.
3. **Moving a live process into a non-leaf cgroup fails: EBUSY.** A cgroup that has
   controllers enabled for its children cannot hold processes
   (`echo $$ > e1/cgroup.procs` → *write error: Device or resource busy*), while the same
   write into the child `e1/leaf` succeeds.
4. **Enabling a controller in a cgroup that already holds a process fails: EBUSY (errno 16)** —
   the "no internal processes" rule, proven directly.
5. **A child of a cgroup that never enabled a controller has NO limit files at all** —
   `e2/leaf2` lists only `cgroup.*`, `*.pressure` and `cpu.stat`/`cpu.stat.local`, and
   **has no `memory.max`**. This is the silent no-op the brief predicted: nothing fails,
   the limit simply cannot be expressed there.
6. **Threaded targets are unusable for placement:** after `cgroup.type=threaded`,
   writing a thread-group id to `cgroup.threads` → **EOPNOTSUPP (95)**, and writing a
   process to `cgroup.procs` → **EOPNOTSUPP (95)**. Unit places applications by writing
   `cgroup.procs`, so a threaded target cannot work.
7. **A systemd service without `Delegate=yes`:** the unit's own cgroup has `memory.max`
   (systemd can limit the service itself; `controllers: memory pids`, `subtree_control:`
   empty) but a **child of it has NO `memory.max`**, and enabling `+memory` on the service
   cgroup by hand fails with **EBUSY** because the service already holds its processes.
8. **`Delegate=yes` alone does NOT fix it.** The delegated service cgroup still showed an
   empty `subtree_control`, its child again had no `memory.max`, and the manual
   `+memory +cpu` write failed with **EBUSY** for the same reason (the cgroup holds
   processes). Conclusion: on systemd, delegation must be combined with a
   **process-free parent** for the app cgroups, or the limits stay unreachable.
9. **Rootless works only inside the user manager's own subtree:** the user manager cgroup
   (`user.slice/user-<uid>.slice/user@<uid>.service`) already has
   `subtree_control: cpu memory pids`, a non-root user CAN `mkdir` there, and the created
   child carries the full limit file set. Anywhere outside that subtree the user cannot
   create cgroups at all.

Consequences for the product (to be confirmed in phase B, live, with unitd):

- The config surface (`path` only) is not the whole story: with a RELATIVE path Unit
  creates the leaf under **unitd's own cgroup**, which by construction holds unitd's
  processes → per finding 3/4 that leaf can never receive limit files. The usable recipe
  is an **absolute** path into a process-free, controller-enabled parent.
- The documentation delta is therefore two sentences, not one: *Unit places the
  application; the operator creates a process-free parent with the controllers enabled
  and sets the limits there* — with a per-platform recipe (systemd: a delegated, empty
  parent; container: the runtime's cgroup parent; bare cgroupfs: `mkdir` + `+cpu +memory`).
- Threaded targets (finding 6) deserve an explicit, loud refusal rather than a generic
  failure — that is a candidate code finding, not a docs note.

## 2c. Probe results — phase B, with unitd running (2026-10-11, live)

Same stand class (Scaleway DEV1-M, **Debian 13 Trixie, kernel 6.12.111, 3 vCPU**).
FreeUnit built from `master` with the Python module, **`unitd 1.37.0`**, run as a
systemd service with `Delegate=yes`. All lines below are live observations.

**Build recipe verified (the module is a SECOND configure pass):**
`./configure --prefix=/usr/local --statedir=/var/lib/unit` → `rc=0`, then
`./configure python --config=python3-config` → `rc=0`, *"configuring Python module …
+ Python module: python3.unit.so"*, `make`/`make install` clean, module installed as
`python3.unit.so`. Without the common pass the module pass refuses
(*"Please run common configure before configuring module"*), and with no module at all
every `PUT /config` is rejected with *The module to run "python" is not found* — so a
stand can look healthy while no application can start at all. Debian needs
`libpcre2-dev` for the common pass.

1. **RELATIVE `path` places the app but leaves no limit surface.** With
   `"isolation": {"cgroup": {"path": "fu/app"}}` the PUT answers *Reconfiguration done*,
   the app starts and serves (`200 ok pid 5413`), and Unit creates
   `/sys/fs/cgroup/<unitd's service cgroup>/fu/app` holding the app's pids. The leaf
   contains **no `memory.max`, no `cpu.max`, no `pids.max`, no `memory.current`** — only
   `cpu.pressure`, `cpu.stat`, `io.pressure`, `memory.pressure` and the `cgroup.*` files.
   The limit surface simply does not exist there, exactly as the earlier "no controllers
   enabled in the parent" case predicts. The app runs happily; nothing warns.
2. **ABSOLUTE `path` into a process-free, controller-enabled parent gives the full limit
   surface.** `mkdir /sys/fs/cgroup/fuapps` + `echo '+cpu +memory +pids' >
   fuapps/cgroup.subtree_control`, then `"path": "/fuapps/app"` → `/sys/fs/cgroup/fuapps/app`
   carries `memory.max`, `memory.high`, `memory.swap.max`, `cpu.max`, `cpu.weight`,
   `pids.max`, `memory.oom.group`, and `memory.max=64M` / `cpu.max=50000 100000` /
   `memory.oom.group=0` are all accepted. **This is the operator recipe.**
3. **Throttling is real and measurable.** Two CPU-bound requests under a 0.5-CPU quota:
   `cpu.stat` moved from `nr_periods 1 / nr_throttled 0` to **`nr_periods 25 / nr_throttled 24
   / throttled_usec 3 452 680`** (~1.35 s of CPU work). A quota below the work stalls it in
   100 ms slices; the limit caps time, not concurrency.
4. **Per-app OOM (measured).** Under `memory.max=64M`, a request that allocates ~160 MB
   returns **HTTP 503**; `memory.events` = **`max 37, oom 1, oom_kill 1, oom_group_kill 0`**,
   `memory.peak` = `67 108 864` (the cap exactly), the log shows
   *app process … exited on signal 9*, **unitd survived** and respawned the app, and the
   next request returned 200 with a new pid. So with `oom.group=0` the kernel kills ONE
   process of the app, not the cgroup, and Unit's supervision turns it into a restart.
5. **The CPU-limit derivation is visible in the product.** With
   `systemctl set-property unit.service CPUQuota=100%` the service cgroup shows
   `cpu.max 100000 100000` and `unit.log` carries
   **`the cgroup CPU limit lowers the CPU count from 3 to 1`**; router threads dropped
   4 → 2 in the same comparison (no quota: 4). The record is written at startup, i.e. a
   quota change needs a restart to take effect — and with no quota no record is written.
6. **Throughput: no claim made.** Same `ab -k -n 4000 -c 50` against the Python WSGI app:
   with the 1-CPU service quota **3502 rps**, without it **2927 rps** — single runs, the
   gap is inside run-to-run noise and the app does not saturate 3 vCPU. Recorded here only
   as "the thread-count reduction did not visibly hurt", NOT as a performance result.
7. **OPEN — threaded target.** Unit accepted `"path": "/e4/t"` into a cgroup whose
   `cgroup.type` is `threaded` (*Reconfiguration done*) and the app served 200, while our
   direct kernel-level write of a process into a threaded cgroup failed with
   `EOPNOTSUPP` (phase A, finding 6). Which cgroup the app's processes actually landed in
   was **not** verified in this run — one check away (`cat /proc/<app pid>/cgroup`), and it
   decides whether the kernel tolerates Unit's placement there or Unit silently left the
   process where it was.

## 2d. Probe results — phase C, the threaded-target question (2026-10-11, live)

Purpose: decide the leftover item from §2c.7. Fresh stand, same class (Debian 13 Trixie,
kernel 6.12.111, 3 vCPU), FreeUnit built from `master` (common configure + python module
pass, `unitd 1.37.0`), app = Python WSGI, config uploaded with `PUT /config`.

**Control (domain target).** `"path": "/plain/app"` → *Reconfiguration done*, the app answers
`200 ok pid 5365`, `/proc/5365/cgroup` reads **`0::/plain/app`**, and both the prototype and
the app pid are listed in that leaf's `cgroup.procs`, `cgroup.type: domain`. Normal.

**Threaded target.** `/thr/t` with `cgroup.type=threaded`, parent a normal domain cgroup:

- A direct kernel write of a process into it (python writing its own pid) fails with
  **`EOPNOTSUPP` (errno 95)** — reproducing phase A, finding 6.
- Unit's config is nevertheless **accepted**: `PUT` → *Reconfiguration done*, the app starts
  and serves, and `/proc/<app pid>/cgroup` reads **`0::/thr/t`** — i.e. Unit **does** place the
  application inside a threaded cgroup, and the prototype and the app process both end up
  there (they appear in `cgroup.threads` on the first attempt).
- The two attempts were **not identical in bookkeeping**: after a unitd restart, that same
  cgroup listed the prototype and app pids in **`cgroup.procs`** as well, while on the first
  attempt only `cgroup.threads` held them. Recorded as an observation about when Unit writes
  the pid, not as a defect claim.
- `unit.log` shows an ordinary start-up sequence (`prototype started`, `application started`)
  with **no refusal or error line** about the threaded target.

**What this settles and what it does not.** Settled: the earlier A3/§2c.7 suspicion was wrong —
Unit's placement into a threaded target does not fail; the kernel refuses a *bare* process
write from outside the threaded subtree, which is not the same operation Unit performs at that
point in the app's life. Not settled (still open, and the reason the item stays in the brief):
whether a threaded target can carry the per-app limits at all — the run did **not** capture the
threaded cgroup's file list or attempt to write `cpu.max`/`memory.max` there, so no claim is
made about the CPU-bandwidth or memory interface in threaded mode. Product question that
remains: should a threaded `path` be accepted silently, or refused/warned about when the user's
intent is evidently a limit?

## 2e. Probe results — phase D, CLOSED: a threaded cgroup carries no limits (2026-10-11, live)

Same stand class (Debian 13 Trixie, kernel 6.12.111, 3 vCPU), unitd 1.37.0, app = Python WSGI.

**Control (domain target `/dom/app`)** — full interface present and writable:
`memory.max max`, `cpu.max max 100000`, `pids.max max`, `cpu.weight 100`, `memory.current`,
and `echo 64M > memory.max` accepted (`rc=0`).

**Threaded target (`/thr/t`, `cgroup.type=threaded`)** — the interface is **absent**:
the directory lists only `cgroup.*`, `cpu.pressure`, `cpu.stat`, `io.pressure`,
`memory.pressure`. There is **no `memory.max`, no `cpu.max`, no `pids.max`, no
`memory.current`, no `cpu.weight`, no `memory.oom.group`**, and an attempt to write any of
them fails with **EACCES (errno 13)** — cgroupfs refuses to create a file the kernel does not
expose there (a plain `open(O_CREAT)` on a nonexistent cgroup file returns EACCES, not ENOENT).
The second threaded variant (`/thr2/t2`, also `threaded`) shows the identical empty interface.

**Unit's behaviour is unchanged by that**: `PUT` → *Reconfiguration done*, the app starts,
serves, and `/proc/<pid>/cgroup` reads `0::/thr/t` (and `0::/thr2/t2`), with the prototype and
the app process in `cgroup.threads`. `unit.log` carries no refusal about the target; the only
line in that window is a teardown artifact of the previous instance
(`sendmsg(...) failed (32: Broken pipe)`), not a placement error.

**Conclusion (the item is closed).** A user who points `isolation.cgroup.path` at a threaded
cgroup gets a placed, running application and **no way to limit it** — the CPU, memory and pids
interfaces do not exist in threaded mode, and Unit neither warns nor refuses. That is a product
decision, not an open measurement: either the config should be refused/warned at validation
(the operator's evident intent when naming a cgroup is to limit it), or the docs must state the
limitation. Combined with §2c.1, the same silent-unenforceability now has two confirmed
shapes: **relative path** (no interface because the parent enables nothing) and **threaded
target** (no interface by kernel design).

## Related

- `engineering/seccomp-isolation-plan-summary.md` — syscall policy half (decided)
- `engineering/readiness-capget-rootfs.md`, `engineering/capget-fallback-plan.md` —
  adjacent isolation-side fixes
- `engineering/fork-spawn-drupal-measurement.md` — the shared-opcache memory numbers
- `releases/1.37.1-plan.md` — the release that gates this work
