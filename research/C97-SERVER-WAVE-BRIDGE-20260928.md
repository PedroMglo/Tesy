# C97 server wave bridge after C96 prelaunch failure

- Objective: rerun the paired C35/C75 two-turn 8K actual-history bridge under a new campaign identity, after a model-free repair of C96's sequential receipt/worktree conflict.
- Base: C96 result commit `f3b62e7`; C96 control passed, candidate was `NOT_RUN_MODEL` after a harness prelaunch failure. Both remain preserved. C93–C95 same-profile numeric gates passed observed scope.
- Fix: C97 writes interim arm receipts inside the ignored campaign `raw/` directory and checks the prior control receipt there. A directed test reproduces that a new receipt in this location leaves the measurement tree clean and rejects missing/failed/incomplete prior receipts. The final compact receipts and hashes will be copied into Git only after physical execution.
- Hypothesis and alternative: same as C96. C35 control followed by C75 candidate; fresh process per arm. Synthetic 1960-word prefix and real assistant answer on turn 2. One pair is a serving bridge, not a performance promotion or diverse quality evaluation.
- Frozen gates: E18/zero swap and current resource-policy snapshot; model/backend/binary/mapped libraries, official token IDs, generated-history cache bounds, full finite responses, final content, stream completion, monotonic request markers and telemetry. First failure closes its run. Do not reuse any C96 run ID.
- NOT_RUN at freeze: C97 model, alternating performance screening, M3 diverse/active sustained test, M4 quality and latency qualification.
- Next gate if both arms pass: compare official token IDs and outputs; choose a separately frozen alternating screen only if the bridge has comparable inputs and no resource/fidelity failure.

## Result

- Measurement commit: `586aa5488af58a8faa6159e8b53dead18017a55b`. Control C35 passed both turns: first request 2043 prompt/77 completion tokens, 300.398 s; second 2081 prompt/60 completion tokens, 2044 cached, 28.646 s. Cgroup peak 13,145,841,664 B, GPU total 5752 MiB, CPU 95.125 °C, swap zero. Evidence: MEDIDO_NO_TARGET, synthetic one-arm bridge.
- Candidate `c97-candidate01` failed before model launch. Its extra port precheck used `bind` without `SO_REUSEADDR`; an independent socket inspection found port 18367 in `TIME_WAIT`, with no listener. Preserve `FAIL_HARNESS_PRELAUNCH` and `NOT_RUN_MODEL`. This is not a C75 result.
- C97 control is a valid contemporary comparator for a new C98 candidate identity if its raw and compact hashes remain valid. C98 must remove the redundant bind and rely on the existing server runner's `SO_REUSEADDR` check. No C97 candidate ID is reused.
