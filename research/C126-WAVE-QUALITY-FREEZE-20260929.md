# C126 — C75 quality qualification on the frozen C40 tasks

Objective: evaluate the C75 waves candidate on the same twelve tasks, inputs,
template date, medium effort, sampling, output cap and validators that C40 P12
resolved 12/12. The C40 result remains the independent control; this is a
functional no-loss check, not a causal speed comparison or broad quality claim.

Base: C125b result HEAD `08cfb0683887df53bc541f951114c6436050993c`.
Source/profile: original C75 backend `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`
with `TESY_CPU_WAVE_SKIP_PARKED=1`, P12, 32 expert slots per layer, ubatch32,
preload ON, context8192, F16 unified/offloaded KV, original GPT-OSS120B MXFP4.
The full binary/library/model identities are frozen in the arm protocol.

Workload: `workloads/c38_quality12.json`, date 2026-09-28 in each evaluation
task, medium, temperature0, seed42, cap3072, up to600 s per request. The
12 validators in `tools/c38_quality_grade.py` were frozen by C40; its model-free
gold/mutant self-test is required before freeze. No task selection after output.

Admission: one E18/zero-swap server process, a fresh resource snapshot and
policy v2, a strong 60 s per-arm inventory, age <=3 s at Popen, prospective
resource monitoring and receipt validation. The existing C120 entrypoint gate
is reused. The frozen protocol and measurement commit precede the model run.
Worst-case reservation is 6000 s server + 60 s inventory + 600 s closure.

Decision: `PASS_QUALITY_12_OF_12` only if all 12 complete naturally, official
tokenization and resource/identity receipts pass, and all twelve frozen
validators pass. Any task failure is retained as `QUALITY_NO_LOSS_FAIL`;
infrastructure or resource failure has its own status. Historical C100/C117
failures remain unchanged. Holdout8, diverse assistant-history continuity,
active >=15 min and the M4 latency gates are separate NOT_RUN here.

Tests before physical execution: C40 gold/mutant validator self-test PASS;
source syntax and model-free protocol construction PASS. Full C126 live result
is NOT_RUN at this source checkpoint.
