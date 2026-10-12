---
title: Port fragmentation hardening — eviction and the convergence criteria
description: Why #447's 64-stream cap is bypassable (no time bound), the standard fix (eviction/timeout), the structural fix (refuse fragments from untrusted senders), and falsifiable exit criteria for the whole "untrusted shared-memory" bug class.
tags: [port, frag, hardening, uaf, dos, convergence]
status: analysis
updated: 2026-09-25
resources:
  - https://github.com/freeunitorg/freeunit/pull/447
  - https://github.com/freeunitorg/freeunit/issues/172
---

# Port fragmentation hardening — is the rabbit hole finite?

Andrey: *"эта кроличья нора имеет свет в конце?"* Short answer: **yes, and you are
near it — but the exit is a bound on the third axis, not the next check.**

## The bypass

#447 bounds fragment reassembly by **count** (64 open streams) and **bytes**
(128 MiB/stream, 256 MiB/port). Memory DoS is closed. But a hostile peer can open
64 streams with distinct ids and **never send the last fragment**: all 64 slots
are held indefinitely, `nxt_port_frag_start()` refuses every new stream, and
legitimate fragmented traffic on that port (e.g. controller→router config) stops.
Fix cost to the attacker: ~1 MiB, no further action.

The bound is not wrong — it is **incomplete**. Count and bytes are bounded;
**time is not.** "Hold a slot forever" is a distinct, unbound resource.

## The fix (standard, small)

Bound the **time** dimension, exactly as count and bytes already are:

1. **Timeout eviction.** An incomplete stream is dropped after T of no progress.
   Legitimate reassembly is one buffer split into a handful of back-to-back
   frames — it completes in microseconds-to-milliseconds, so a T of a few seconds
   is orders of magnitude above any real completion and never fires on legit
   traffic. On drop: free the slot, alert.
2. **Evict-oldest on pressure (optional).** When all slots are full and a new
   stream starts, evict the oldest incomplete stream so a new (possibly legit)
   stream always makes progress. Guarantees liveness, not just that the cap holds.

This **closes the class**: once count + bytes + **time** are all bounded, "hold
forever" no longer exists, so neither does this bypass. It is not a new hole —
it is the missing third face of the same bound.

## The structural fix (better, if the trust model allows)

#447 itself notes *"only FreeUnit's own processes fragment messages."* If **apps
never legitimately send fragments** — the fragment path is Unit-internal
(controller→router, etc.) — then the terminal fix is to **refuse fragment streams
from untrusted senders entirely.** The attack surface disappears instead of being
bounded. Worth verifying: can an application process reach `nxt_port_frag_start()`
at all? If not, reject non-privileged fragment openers and the count/byte/time
caps become pure defense-in-depth.

## Why it feels infinite — and why it isn't

The **nature of the findings changed**, which is the signal you are at the last
mile:

- Early findings: *no bound at all* (unbounded reads, unbounded streams).
- This finding: *a bound is bypassable* — you added count+bytes, the attacker
  found the axis you did not bound (time).

You are no longer discovering new classes; you are completing the last dimension
of the class you already fixed. That is convergence, even though the tooling
(Codex, the fuzzers) keeps producing items.

## Falsifiable exit criteria for the "untrusted SHM" class

The class terminates when **all three** hold for the port layer:

1. **Every incompletable resource is bounded on three axes** — count, bytes,
   **and time** (with a pressure policy: evict-oldest / reject-new).
2. **Every value read from shared memory is read once** into the reader's own
   copy before use — never re-read, never trusted after a check (#445 records,
   #468 request). This closes "peer rewrites between check and use".
3. **Where a trust decision is made, the sender is authenticated** by the kernel,
   not by peer-provided fields (SCM_CREDENTIALS / PROCESS_READY by kernel pid —
   `4c79840d`, `#341`/`#172` follow-ups).

When (1)+(2) hold on the port path, the "hostile peer holds or rewrites
shared-memory state" family is closed. (3) is defense-in-depth on top.

**Do not** measure progress by finding count — measure it by axes closed.
`#445`/`#468` close axis 2; `#447` + the timeout close axis 1 for fragments;
`#341`/PROCESS_READY cover axis 3. After that, the remaining wave is features
(h2, schedules), not this bug class.

## Why it surfaced *now* — provenance (verified against `origin/master`)

The class is **latent, not new**. Two adjacent workstreams removed the accidental
masking that had hidden it — matching @andypost's observation: *"тут оно тоже
после ремонта вебсокетов вылезло и после оптимизации выделения памяти."*

**1. Websocket repair** (merge `f9ea6dbe`, 2026-09-23 — #429/#430/#435, plus the
java one-frame and ASGI/`max_frame_size` work) pushed **bigger, fragmented
messages** through the port path (java async **16 MiB**, ASGI now >1 MB). That is
what exercises the fragment-reassembly accounting and the message-length handling
— and what exposed the unbounded reassembly and the length/id bombs.

**2. Memory-allocation optimisation** changed **buffer lifetime and reuse** in the
port path:

- `fc5f08e1` Remove `nxt_mem_zone`, an unused second allocator (2026-09-14)
- `0a4d9a23` port: re-arm a port without allocating (2026-09-14)
- `ca47160b` port: drop the dead tracking bitmap from the shm segment header (2026-08-18)
- `0c0f9811` port: defer the last reference drop with an embedded work item (2026-09-08)

These recycle/free port buffers in ways that make "peer writes after the reader
checked" and "freed buffer reused" (the #447 UAF) **reachable**.

**Timeline (`origin/master`):** alloc opt 2026-08-18 / 09-14 → WS repair 2026-09-23
→ read-once + bounds land 2026-09-27 (`23da8897` #445, `9289c02d` #505,
`0f0eada9` #447). The class surfaced **and** was fixed *after* the two workstreams —
exactly as observed.

**It is a recurring theme, not a one-off.** The same class was already being closed
in July (`669987d6` bounds-check untrusted shmem offsets, 2026-07-06; `58d4a08f`
validate peer-supplied incoming mmap id + geometry, 2026-07-27). The wave is working
down a **latent backlog** that two features detonated — which is why it feels
endless but is finite: the fixes target the *principle* (read-once + bound on
count/bytes/time), not one symptom.

**Merge state:** #445, #505 and #447 are **in `origin/master`**; #448 (queue retry
budget) is **not yet**.

## Mapping the in-flight PRs onto the axes (verified 2026-09-25)

| PR | What it bounds | Axis |
|----|----------------|------|
| **#445** (already in master) | record fields read once into the reader's copy | 2 |
| **#447** | fragment streams: 64 / 128 MiB-per-stream / 256 MiB-per-port, **+ `nxt_port_frag_evict()` evict-oldest on a new stream**, + fixes an **app-triggerable UAF** (mmap fragment with no record → buffer reused) | 1 (partial) |
| **#448** | SHM queue retry budget = one queue size → enqueue `NXT_ERROR`, dequeue empty (no spin-forever on a bad cycle value) | 1 (termination) |
| **#505** | segment ids: `NXT_PORT_MMAPS_MAX` = 65536 → no "id 100000000 → allocate 100 M slots" bomb | 1 + 2 |
| **#468** | request read once | 2 |
| **#341 / PROCESS_READY** | sender authenticated by the kernel, not peer fields | 3 |

### Does #447 close the bypass? Yes — the fix is already in it

The quoted bypass (open 64 streams, never finish → every new stream refused) is
**already handled by #447 as written**: `nxt_port_frag_evict()` drops the oldest
stream when a new one starts and 64 are open — "*streams that a peer never ends
cannot block reassembly for good.*" So legít traffic always makes progress; the
rabbit hole the question describes is closed by the PR, not pending on a new one.

**Residual (minor):** #447 evicts on **pressure**, not on **time**. A held set of
incomplete streams with *no* new traffic (≤64 streams, ≈≤1 MiB) is retained
indefinitely. Not a DoS — new streams evict — but an idle **timeout** would clean
it and fully close axis 1 for fragments.

### Verdict

- **#447 + #448 + #505 close the DoS / memory-safety class** on the port layer —
  every unbounded resource (stream count/bytes, queue retries, segment ids) gets a
  cap, and the record/id reads are bounded on read. Axes **1 + 2** are closed.
- **They do not close the trust class (axis 3).** A hostile peer can still *send*
  and *forge* messages; these PRs bound the **cost**, not the **authority**. Sender
  authentication (kernel-verified pid) is #341 / PROCESS_READY, a separate lever.

### Release-policy note

#447 carries an **app-triggerable use-after-free fix** (its own "Security
changelog entry") — that is patch-worthy per the project's semver rule (patch =
security/DoS). The fragment limits and eviction around it are hardening/feature.

### Merge order / conflicts

`#445` (in master) → `#505` (clean vs master) → `#447` → `#448` (based on #447, is
`dirty` → needs rebase). `#447` and `#505` both add a top `CHANGES` entry, so
whichever merges second needs a one-line changelog rebase.

