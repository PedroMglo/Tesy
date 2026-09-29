# C130 — slots40 original twelve-task quality gate

Objective: determine whether the confirmed C75 waves-ON slots40 profile
retains the 12 functional tasks passed by the independent C40 P12 control
and C126 C75/slots32. Alternative: a new numeric profile changes outputs
or fails a task despite the short C127 numerical admission.

Use the original `workloads/c38_quality12.json`, `c38_quality_grade.py`
validators and per-task caps: medium, temperature0, seed42, max3072 output
tokens, context8192,600 s per request, natural stop. Prompts and validators
are frozen before this candidate's answers. The server/profile and resources
match C126 except `--moe-stream-cache 40s`; C75 waves ON, P12, ub32,
preload, full SWA, F16 unified/offloaded KV, E18 and swap0 remain fixed.
The C126 strong inventory, actual-launch freshness, monitor, receipt and
quality grader path is reused. The wrapper records its own source hash and
the C129 confirmation decision hash in the numeric profile.

Gate: all 12 validators PASS, all 12 requests end naturally with valid
official token counts and no resource/identity/inventory failure. Then
compare each official prompt array and final assistant message with the
historical C40 P12 raw; equal messages support no observed loss on these
tasks but do not prove broad quality. Different yet passing messages are
reported as such, not silently equated. No paired latency speed claim is
made from C40 across days.

The source code and model-free reconstruction are committed before a fresh
60 s host inventory and protocol freeze. One bounded server process only;
timeout6000 s, plus inventory/closure and a future qualification reserve
are admitted before launch. Holdout8 remains a distinct prospective unit
with fixtures and validators frozen before any candidate answer. No default
or remote change. C100/C117 original decisions remain preserved.
