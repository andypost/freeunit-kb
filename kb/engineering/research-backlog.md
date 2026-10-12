# Research backlog — what is worth investigating next (2026-10-11)

Written while the Oracle Cloud stand is being installed: everything below is pure
reading and measurement against the tree and the trackers, so none of it needs the
stand. Items that do need hardware are marked. The 62 open issues in
`freeunitorg/freeunit` are the raw material; each cluster was read from its titles
and, where it mattered, from the tracker.

Already covered, do not repeat: TLS 1.3 and the cluster case, HTTP/3, the TLS module
prototype, code volume and release delta, the 1.37.1 forecast, dependency and CI
hygiene, webhook reaction quantization.

## Ranked candidates

| # | Cluster | Issues | Why now | Needs stand |
|---|---|---|---|---|
| 1 | **CI shape and cost** | 654, 402, 655 | Measurable today from the Actions API: job count per event, wall time, the longest leg, the sleeping-test tail. Every other stream pays this bill. | no |
| 2 | **libunit ↔ router IPC lifecycle** | 669, 668, 667, 665, 663, 662, 425, 443 | The class that produced the 1.37.0 websocket and claim/ack defects. One failure taxonomy over the port, queue and shared-memory lifecycle: claimed-not-acknowledged, drain timeout, wake-up inside the free path, backoff on FULL, teardown keyed off `link.next`. Also names the missing test (`#662`: no test starts a thread). | no |
| 3 | **CVE backlog map** | upstream advisories vs the fork | Which upstream Unit CVEs the fork carries, which it never had, which are unfixed. Goes straight into release notes and any adoption conversation. | no |
| 4 | **ACME / automatic certificates** | 650 | Direct input to the 1.38 TLS priority: client choice, HTTP-01 versus TLS-ALPN-01, storage in the state directory, rotation through the control API, and how it meets the TLS module and SNI. | no |
| 5 | **Timeout and buffering semantics** | 540, 666, 647, 541, 525 | `limits.timeout` doing two jobs, the first body part leaving uncompressed, a short access-log write losing a record, the non-atomic state store. This is also the input D3 (body streaming) needs. | no |
| 6 | **Static file serving contract** | 559, 546, 391, 356 | What the static handler promises versus what it does: MIME table policy, refusing a file only when it exists, HEAD without content-coding headers, ETag blind to a same-size rewrite inside one second. Feeds docs, tests and release notes. | no |
| 7 | **Language module health matrix** | 531, 492, 488, 555, 365 | One table: open bug per module, what CI covers, what has no test. Cheap, and it exposes the module with no coverage before a release claims support. | no |
| 8 | **32-bit correctness class** | 619, 632, + the two already fixed | A dossier of every width assumption (off_t, size_t, size options at 2^31, pool arithmetic) and the probe list to run on the stand. The fixes are needed; the class analysis is not. | partly |
| 9 | **PHP worker mode readiness** | 596, 597 | The two roadmap trackers against what exists: gates, waves, and the `drupal_static` reset options. Sets the next wave's brief. | partly |
| 10 | **Kubernetes deployment posture** | — | Manifests, probes, secret rotation, resource limits, rootless and read-only rootfs. The testable half of the cluster case that the TLS research only described. | partly |

## How each one ends

Every candidate produces the same shape of artifact, so none of them can drift:

1. one KB note under `engineering/`, with file and line evidence;
2. the numbers quoted with the command that produced them;
3. a `(unverified)` marker on anything not checked;
4. an explicit "do not claim" list where the topic is public-facing;
5. board rows only for the actions that follow from it.

## What the stand unblocks when it is ready

- The 32-bit probes and a green 32-bit build (the missing CI gate, #632).
- aarch64 build and test timings against x86_64, three runs each.
- Sanitizer and fuzzing runs that no CI job performs.
- The metric collection described in `oracle-cloud-arm-stand.md`.

## Related

- `engineering/oracle-cloud-arm-stand.md` — the stand plan and its metric set
- `engineering/webhook-reaction-quantization.md` — the completed design note
- `engineering/release-1.37.1-forecast.md` — the 1.37.x shortlist and the 1.38 order
