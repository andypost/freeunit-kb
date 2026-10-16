# cgroup limits — documentation delta, ready to apply (2026-10-11)

**Status: text ready, not applied.** The bot has no write access to `freeunitorg/docs`
(the workbench App is installed on `freeunitorg/freeunit-exp` only; the personal PAT is
read-only — both attested by a non-mutating PATCH probe returning 403). The owner applies
this, or adds `docs` to the App installation and it becomes a bot PR.

Target file: `source/configuration/index.rst`, section **"Using control groups"**
(`.. _conf-app-cgroup:`), directly AFTER the "basic use case" block that ends with
"refer to the admin guide" and BEFORE the following `.. note::` about
namespaces/cgroups versus cgroup/path.

## Why: what the current text assumes and what the live probes showed

The current section documents `path` (relative vs absolute) and a "basic use case" that
writes `memory.high` by hand. It never says **where** a limit can exist. Measured on
Debian 13 Trixie (kernel 6.12.111) with unitd 1.37.0 (`engineering/cgroup-v2-isolation-performance-brief.md`):

- A child cgroup has an interface file for a controller **only if its parent enabled that
  controller in `cgroup.subtree_control`**. Without it there is no `memory.max`/`cpu.max`
  in the app's cgroup at all — nothing fails, the limit simply cannot be expressed.
- A cgroup that has controllers enabled for its children **cannot hold processes**
  (`cgroup.procs` write → `EBUSY`), and a controller cannot be enabled in a cgroup that
  already holds processes (`EBUSY`, errno 16). A **relative** `path` therefore lands inside
  Unit's own cgroup, which by construction holds Unit's processes: limits there are
  **unreachable**, while the app still runs and serves normally.
- An **absolute** path into a process-free parent with the controllers enabled gives the
  full interface (`memory.max`, `memory.high`, `memory.swap.max`, `cpu.max`, `pids.max`,
  `memory.oom.group`), and the limits are enforced (measured: `nr_throttled 24 / 25` periods
  at a 0.5-CPU quota; a 64M `memory.max` produced `oom_kill 1`, an HTTP 503 for the offending
  request, and Unit respawned the app).
- A **threaded** target (`cgroup.type=threaded`) is accepted by Unit and the app is placed
  inside it, but whether it can carry limits was a separate question when this text was
  written; the brief's phase D probe answers it — a threaded cgroup carries no limit
  interface at all.

## The inserted text (RST, paste-ready)

```rst

Where a limit can live
----------------------

Unit *places* the application in the cgroup you name;
it never writes a limit file itself.
A cgroup carries the interface file of a controller
(for example, **memory.max** or **cpu.max**)
only when its **parent** enables that controller
in the parent's **cgroup.subtree_control**;
otherwise the file does not exist in the app's cgroup
and a limit simply cannot be set there,
without any error from Unit.

Enable the controllers you intend to use
in a cgroup that will be the **parent** of the app's cgroup,
and keep that parent **free of processes**:
a cgroup that has controllers enabled for its children
cannot hold processes of its own (**cgroup.procs** writes fail with **EBUSY**),
and a controller cannot be enabled in a cgroup that already holds processes.

.. note::

   Because of the rules above,
   a **relative** **path** is not usable for limits:
   Unit creates it inside its own main-process cgroup,
   which always holds Unit's processes,
   so the controllers cannot be enabled there
   and the app's cgroup has no limit interface at all.
   Use an **absolute** **path** under a process-free parent
   when you intend to limit the application.

Recipes per platform:

.. code-block:: console

   # systemd: delegate the service, then give the apps a process-free parent
   $ systemctl edit unit
       [Service]
       Delegate=yes
       DelegateControllers=cpu memory pids
   $ systemctl daemon-reload && systemctl restart unit
   # the app cgroup must NOT be the service cgroup itself:
   #   { "isolation": { "cgroup": { "path": "/apps/drupal" } } }
   $ mkdir -p /sys/fs/cgroup/apps
   $ echo '+cpu +memory +pids' > /sys/fs/cgroup/apps/cgroup.subtree_control
   $ echo 512M > /sys/fs/cgroup/apps/drupal/memory.max

.. code-block:: console

   # bare cgroupfs (no service manager)
   $ mkdir -p /sys/fs/cgroup/apps
   $ echo '+cpu +memory +pids' > /sys/fs/cgroup/apps/cgroup.subtree_control

   # container: the runtime's cgroup parent is delegated by the runtime;
   # point "path" at an absolute path under it and set the limits from the host.
```

## Open items before this can be merged

1. **RESOLVED 2026-10-11 (phase D probe).** A `cgroup.type=threaded` target carries **no**
   `memory.max`, `cpu.max`, `pids.max` or `memory.current` at all (writes fail with EACCES
   because cgroupfs exposes no such file there), while Unit still accepts the config and places
   the app inside it. So the docs must state that a threaded cgroup cannot be limited, and the
   product question (warn at validation vs refuse vs document) goes to the maintainer. Add one
   sentence to the inserted `.. note::` when that decision lands.
2. `DelegateControllers=` requires a systemd new enough to accept it; the recipe must name
   the fallback for older systemd (create the parent by hand as root, as in the second block).
3. English prose style: the project's docs use one sentence per line — keep that when applying.
