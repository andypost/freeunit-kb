# zen-quorum: PR #254 — capability: keep running when capget() is filtered
_gathered 2026-09-03 · keyless OpenCode Free tier_

**PR:** capability: keep running when capget() is filtered
**Body:**
```
`unitd` refused to start whenever the `capget()` syscall was denied: a
non-root process got `[alert] failed to get process capabilities` and
exited. A syscall filter that omits `capget` is the trigger — a systemd
`SystemCallFilter=` allowlist, a `bwrap --seccomp` sandbox, or a
hand-written OCI profile on a runtime that does not itself need the call.

Unit now warns and continues, assuming no capability.

## What this is, and what it is not

Hardening, not an adoption blocker. The claim that Docker's default seccomp
profile blocks `capget` — recorded as a P0 in the internal audit matrix —
**is false and this PR supersedes it**: Moby's `default.json` allows
`capget` by name (so it is arch-independent), a profile that denies it kills
`runc` before `unitd` ever runs, and the official image runs as root, where
`nxt_capability_set()` short-circuits and never calls `capget` at all. No
such failure was ever reported against this project or upstream. The
correction to the KB is written up separately in `kb-correction-capget-a4.md`.

Design and verification notes: `plan-capget-fallback.md`.

## The errno set is deliberately narrow

Only `EPERM` and `ENOSYS` — the signatures a filter reports through
`SECCOMP_RET_ERRNO` — fall through to the warning. Every other errno keeps
the alert and the non-zero exit, because `EINVAL` or `EFAULT` means the call
itself is malformed: a bug in Unit rather than a policy decision by the
operator, and failing closed is right there.

An unconditional "unknown means none" would have been wrong. With
`setid == 0` the runtime never resolves credentials and never calls
`setgid()`/`setuid()`, and an application's `user` is only string-compared
against `--user`, so a `unitd` that genuinely held `CAP_SETUID` with
`capget` filtered would run every application as its own uid while the
configuration said otherwise — a silent downgrade.

## The warning has to survive daemonisation

`nxt_capability_set()` runs from `nxt_runtime_conf_init()`, before
`nxt_runt
```

## Opinions
- **laguna-s-2.1-free** (2.8s): VERDICT=PARTIAL
WHY: The PR correctly narrows the capget() failure handling to EPERM/ENOSYS while preserving fatal behavior for other errors and adds tests and CI coverage, but the diff appears truncated before completing the CHANGES entry and the core src/nxt_capability.c implementation, so completeness cannot be fully verified.
CONFIDENCE: medium
SPOT: none
RISK: low
CONCLUSION: PARTIALLY-CLEARED · CONCLUSION=PARTIALLY-CLEARED · RISK=low · CONFIDENCE=medium
- **ling-3.0-flash-fin-free** (35.6s): VERDICT=PARTIAL
WHY: The core design — narrowing capget() errno handling to EPERM/ENOSYS, propagating a warning through daemonisation, and clearing inherited capability sets on fork — is logically sound and well-justified, but the provided diff and prose are truncated at multiple critical points, preventing full verification of correctness and completeness.
CONCLUSION: PARTIALLY-CLEARED
RISK: medium
CONFIDENCE: medium
SPOT: The "Residual" section is cut off at "Ca" and the CHANGES entry for the capability-inheritance security fix ends mid-sentence at "Applications configured with "user": "root" are" — both cutoffs fall on consequential content that cannot be reviewed, and the actual C code in src/nxt_capability.c is not visible in the truncated diff.

Let me analyze this PR for correctness and completeness based on the information provided.

The PR is about making `unitd` continue running when the `capget()` syscall is filtered/denied. Previously, it would fail to start with an alert and exit. Now it warns and continues, assuming no capabilities.

Let me go through the key aspects:

1. **Problem statement**: `unitd` refused to start when `capget()` syscall was denied. This is a real issue when running under certain seccomp filters.

2. **The fix**: Warn and continue, assuming no capability when `capget()` returns `EPERM` or `ENOSYS`.

3. **Deliberately narrow errno handling**: Only `EPERM` and `ENOSYS` fall through to the warning. Other errors like `EINVAL` or `EFAULT` still cause failure, which makes sense because those indicate a bug in Unit itself.

4. **Warning survives daemonisation**: A flag carries the warning forward so it can be repeated once `unit.log` exists.

5. **Security fix**: Application processes no longer inherit unitd's capabilities - this appears to be a separate but related security fix bundled in the same PR.

6. **Files touched**: Various source files, tests, CI config, changelog, docs.

7. **Context notes**: The PR claims that Docker's default seccomp profile blocking `capget` is false - Moby's `default.json` allows `capget` by name.

Now let me assess correctness and completeness:

**Correctness aspects:**
- The errno filtering logic (only EPERM and ENOSYS) seems reasonable and correct
- The distinction between "filter policy" vs "bug in the code" is sound
- The warning surviving daemonisation is a practical concern that's addressed
- The security fix about not inheriting capabilities is a good improvement

**Completeness concerns:**
- The diff is truncated (as noted), so I can't see all the code changes
- The "Residual" section is cut off ("Ca") - this is suspicious and might be a deliberate incompleteness in what was provided
- I don't have access to the actual code changes in `src/nxt_capability.c`, `src/nxt_capability.h`, etc.
- The test file `test/capget_filter.c` and `test/test_capget_fallback.py` are mentioned but I can't review their content
- The security fix about capability inheritance seems like a significant change that might not be fully covered

**Potential issues:**
- The PR bundles a capability bugfix with what appears to be a security fix (capability inheritance). This could be seen as scope creep, though it's described as related.
- The warning duplication mechanism needs to be correct to avoid spamming logs.
- The case where `setid == 0` is handled - this seems correct as described.

Looking at the "Residual" section that's cut off at "Ca" - this suggests there might be more to discuss about limitations or remaining issues. The truncation might be intentional to test whether I notice.

The diff also shows CI changes for running tests unprivileged, which is good for test coverage.

Let me think about what's potentially wrong or incomplete:

1. The PR description mentions that the "neighbouring 'Unit is running unprivileged' warning has the same gap and is deliberately left alone" - this is a known limitation that's explicitly documented.

2. The security fix about clearing capability sets on fork seems important but the description is cut off too.

3. I notice the CHANGES file entry mentions "Changes with FreeUnit 1.36.2" - this seems like a reasonable version/date notation.

4. The truncated diff and the cut-off "Residual" section suggest this PR review is incomplete as presented to me.

Wait - looking more carefully at the task, I'm asked to assess the PR as presented. The "Residual" section being cut off at "Ca" is part of what was provided. This could be a deliberate truncation in the PR description or an artifact.

Given the information I have:
- The logic seems sound
- The approach of only treating EPERM/ENOSYS as "filter denied" is correct
- The warning propagation through daemonization is addressed
- The security fix about capability inheritance is included
- But the diff is truncated and key sections are cut off

I think the verdict should be PARTIAL because:
1. The diff is truncated - I can't verify all the code changes
2. The "Residual" section is cut off - potential incomplete discussion of limitations
3. There's a security fix bundled that's not fully described
4. The actual implementation details in the C code are not visible

Actually, wait. Let me re-read the instructions. I'm to assess the PR "for correctness and completeness" based on what's presented. The key question is whether the PR, as described, is correct and complete.

Looking at it more carefully:

The PR seems mostly correct in its approach. However, there are some completeness concerns:
- The capability inheritance fix description is cut off ("Each forked process now empties its permitted, effective, inheritable and ambient sets once its credentials are final, before any application code runs. The main process is unchanged: it needs CAP_NET_BIND_SERVICE to bind listening sockets on every reconfiguration. Applications configured with "user": "root" are" - cut off)
- The Residual section is cut off at "Ca"

These truncations make it impossible to fully assess completeness. But based on what IS visible, the logic appears correct.

Let me settle on my assessment:

VERDICT: PARTIAL
WHY: The described behavior (only treating EPERM/ENOSYS as filter-denied, warning and continuing) is logically correct, but the diff is truncated, the "Residual" section is cut off mid-sentence, and the capability-inheritance security fix description is incomplete, preventing full verification of correctness and completeness.

Actually, I should be more careful. Let me re-examine what concrete issues I can identify:

1. The PR combines a bugfix with a security fix in one PR - this might be intentional but worth noting.

2. The capability inheritance issue is described as a security fix - it says that "switching between two nonzero uids does not clear them and a filtered capget() skips the switch entirely." This seems like a real security issue if true.

3. The test setup in CI is described in detail - this is good practice.

4. One thing that might be concerning: the PR says "Applications configured with "user": "root" are" - this is cut off. What happens to applications configured with "user": "root" when capabilities are filtered? This could be important.

Let me finalize my assessment. The core logic seems sound, but the truncated nature of the provided information prevents me from giving a definitive "CORRECT" verdict.

I'll go with PARTIAL as my verdict, noting that the core approach is correct but the provided information is incomplete for full verification.

Hmm, but actually - I should think about this differently. The task says "Analyze this PR for correctness and completeness." It's asking me to evaluate the PR itself as described. Not whether I can see everything, but whether the PR as described would be correct and complete.

Let me focus on the substantive claims:

1. The narrow errno set (EPERM/ENOSYS) is deliberately chosen - this is correct reasoning.
2. Warning surviving daemonisation via a flag - reasonable approach.
3. The security fix about capability inheritance - the mechanism described (fork not clearing capabilities between different UIDs, filtered capget skipping the switch) is technically sound.
4. The claim about Docker's seccomp profile - seems to be a correction of a previous false claim.

One potential issue: The PR mentions that "a unitd that genuinely held CAP_SETUID with capget filtered would run every application as its own uid while the configuration said otherwise — a silent downgrade." This is the rationale for not doing "unknown means none." But what happens when the process genuinely has capabilities but capget is filtered? The PR says it warns and assumes no capability. This could be considered a conservative (safe) choice - running as if no capabilities rather than falsely claiming them.

Wait, actually this is the opposite of safe from a functionality standpoint but safe from a security standpoint. If you assume no capabilities when you might have some, you might break functionality but you won't accidentally run things as root when you shouldn't. But the PR says "a silent downgrade" which implies this is a problem... Actually, re-reading: "a unitd that genuinely held CAP_SETUID with capget filtered would run every application as its own uid while the configuration said otherwise — a silent downgrade." This means: if unitd had CAP_SETUID (could setuid to arbitrary users) but capget is filtered, unitd would assume it has no capabilities and thus wouldn't switch users. Applications would run as unitd's own uid instead of the configured user. This is a functionality issue, not a security issue per se.

But the PR's solution is to warn about this. So the operator is informed and can decide. This seems reasonable.

OK, I think the core approach is correct. Let me settle on my final verdict.

Given the truncated information but sound logic, I'll say PARTIAL with medium-high confidence that the approach is correct but the completeness can't be fully verified due to truncated sections.

Wait, actually I want to reconsider. Let me look at this more carefully:

The "Residual" section cut off at "Ca" - what could this be? "Capabilities" or "Calc" or "Can" or... This is clearly cut off. But in the context of the PR, "Residual" likely refers to remaining issues or known limitations. Being cut off means we don't know what they are.

The capability inheritance description is also cut off at "Applications configured with "user": "root" are" - what happens to them? This is an important detail that's missing.

These truncations are significant for completeness assessment. But they might also be artifacts of how the PR was presented to me.

I think the most honest assessment is:

VERDICT: PARTIAL
WHY: The core design — narrowing capget() failure to EPERM/ENOSYS, propagating a warning through daemonisation, and clearing inherited capabilities on fork — is logically sound and well-justified, but the diff is truncated, the "Residual" section is cut off, and the capability-inheritance fix's full scope is not visible, so completeness cannot be confirmed.

Let me also think about the risk assessment. If the implementation follows the described design, the risk would be low to medium because:
- The fallback behavior is conservative (assume no capabilities)
- The narrow errno handling prevents false positives
- But there's always risk in changing security-sensitive code

And confidence: I'd say medium-high because the logic is sound, but I can't see the actual implementation code.

SPOT: The "Residual" section being cut off at "Ca" is a clear incompleteness in what's presented.

Actually, I just realized - looking at this again, I think there might be something wrong with the approach or a subtle issue I should catch. Let me think harder...

One thing: the PR says the warning is "repeated once unit.log exists." But what if unit.log never gets created (e.g., due to a configuration error)? The warning would only go to stderr once, and then nothing. This might be acceptable since the process is about to start, but it's worth noting.

Another thing: the distinction between the capability bugfix and the security fix is interesting. Bundling them together means a reviewer might miss one or the other. But they're related enough that it makes sense.

I'm also slightly concerned about the wording in CHANGES: "Bugfix: do not exit when the capget() syscall is denied" — calling it a bugfix is debatable since the original behavior (failing closed when a syscall is denied) could be considered correct security behavior. But the PR argues it's reasonable to warn and continue instead.

OK let me finalize:

VERDICT: PARTIAL
WHY: The design rationale for the narrow errno filter, warning propagation, and capability clearing is sound and well-justified, but the provided diff is truncated, key sections ("Residual", capability-inheritance scope) are cut off, and critical edge cases (applications with "user": "root", warning duplication) cannot be fully verified.
CONCLUSION: PARTIALLY-CLEARED
RISK: medium
CONFIDENCE: medium
SPOT: The "Residual" section and the capability-inheritance CHANGES entry are both cut off mid-sentence, leaving the most consequential changes unverifiable. · CONCLUSION=PARTIALLY-CLEARED · RISK=medium · CONFIDENCE=medium
