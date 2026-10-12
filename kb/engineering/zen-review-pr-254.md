## Run 2026-09-03 19:42 · mode=agent

**PR 254:** capability: keep running when capget() is filtered

### tool_calls
- zen_quorum.run_model x2 models
- laguna-s-2.1-free: 16.9s
- ling-3.0-flash-fin-free: 51.9s

### findings
- laguna-s-2.1-free SPOT: The CHANGES entry describes application processes no longer inheriting unitd's capabilities (clearing permitted/effective/inheritable/ambient sets after fork), but none of the shown diffs for src/nxt_capability.c, src/nxt_process.c, or src/nxt_runtime.c include the capability-reduction logic, suggesting either a missing diff or missing implementation.
- ling-3.0-flash-fin-free SPOT: none — but the truncated CHANGES entry `"Applications configured with \"user\": \"root\" are"` leaves a critical edge case (what happens when capget is filtered and `user: root` is configured) unverified, and the separate Security changelog item about clearing ambient/inheritable capability sets on fork is absent from the PR description body entirely.

### verdicts
- laguna-s-2.1-free: VERDICT=PARTIAL
WHY: The PR correctly handles capget() filtering with a narrow errno check and preserves the warning pre-daemonization, but the diff is truncated at "Residual" and omits the actual src/nxt_capability.c/h changes, making it impossible to verify the core logic (e.g., capability clearing post-fork and the flag mechanism), and the CHANGES entry describes a security fix (inheriting capabilities) that the file list claims is part of this PR but the diff snippets do not demonstrate.
CONCLUSION: NOT-CLEARED
RISK: medium
CONFIDENCE: medium
SPOT: The CHANGES entry describes application processes no longer inheriting unitd's capabilities (clearing permitted/effective/inheritable/ambient sets after fork), but none of the shown diffs for src/nxt_capability.c, src/nxt_process.c, or src/nxt_runtime.c include the capability-reduction logic, suggesting either a missing diff or missing implementation. CONCLUSION=NOT-CLEARED RISK=medium
- ling-3.0-flash-fin-free: VERDICT= CONCLUSION=PARTIALLY-CLEARED RISK=medium

------------------------------------------------------------
## Run 2026-09-03 19:40 · mode=agent

**PR 254:** capability: keep running when capget() is filtered

### tool_calls
- zen_quorum.run_model x1 models
- laguna-s-2.1-free: 2.4s

### verdicts
- laguna-s-2.1-free: VERDICT=PARTIAL
WHY: The PR describes a valid and well-reasoned fix conceptually, but provides no actual diff or file changes to verify, making it impossible to confirm implementation correctness or completeness.
CONCLUSION: NOT-CLEARED
RISK: medium — a daemonization-logging gap and narrowed errno handling are subtle and easy to get wrong without seeing the code
CONFIDENCE: medium
SPOT: none CONCLUSION=NOT-CLEARED RISK=medium — a daemonization-logging gap and narrowed errno handling are subtle and easy to get wrong without seeing the code

------------------------------------------------------------
# zen-review history — pr 254
_accumulated context, tool calls, findings, verdicts per run._

------------------------------------------------------------
## Run 2026-09-03 19:40 · mode=script

**PR 254:** capability: keep running when capget() is filtered

### context
- +1024 /-12
- files: .github/workflows/build-test.yml, CHANGES, docs/changes.xml, src/nxt_capability.c, src/nxt_capability.h, src/nxt_process.c, src/nxt_runtime.c, test/capget_filter.c, test/test_capget_fallback.py
- head: fix/capget-fallback
- diff_size: 20000 chars

### tool_calls
- gh pr view --json files,add,del + gh pr diff

### findings
- +1024 /-12
- files: .github/workflows/build-test.yml, CHANGES, docs/changes.xml, src/nxt_capability.c, src/nxt_capability.h, src/nxt_process.c, src/nxt_runtime.c, test/capget_filter.c, test/test_capget_fallback.py
- head: fix/capget-fallback
- diff_size: 20000 chars

### verdicts
- (script mode: facts only, no LLM verdict)
