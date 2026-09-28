# C52b — sustained assistant-history recovery

- Objective: execute the frozen C52 sustained 20-request test under a new identity after its prelaunch argument failure.
- Base: `bf70cae` on `campaign/120b-assistant-history-sustained-20260928-1123utc`. Measurement commit will be sealed after current preflight.
- Evidence: C52 rejected an abbreviated measurement SHA before idle admission or model load. This FAIL remains unchanged. C51 actual two-turn bridge and C37 20-request synthetic session remain separate PASS scopes.
- Alternative: the 20-turn actual assistant-history path may still fail on a later prefix, answer, resource guard or duration gate.
- Protocol: same model/backend/profile, inputs, thresholds, 165-second inter-request idle, 20 requests, >=3600-second session span, 4800-second process timeout and E18 CPU100 resource envelope as C52. Only campaign/root/run IDs and the corrected full measurement SHA invocation differ.
- Tests before model: syntax and 14 focused model-free tests; frozen source, model, binary and input hashes; fresh host/scope preflight and thermal idle admission. Physical result: NOT_RUN at freeze.
- Failure policy: one run, no retry. The first answer/cache/resource violation ends C52b and remains evidence.
- Next gate: if PASS, summarize first/last halves and decide the next M3 latency test. If FAIL, diagnose by the observed reason under a new identity.
