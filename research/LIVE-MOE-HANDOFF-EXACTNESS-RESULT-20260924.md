# Live MoE handoff exactness result

Date: 2026-09-24

Measurement commit: `28b18c7d05bfa921469afa9b32332f5579164f02`.
Campaign: `results/live-moe-handoff-exactness-20260924T180016Z/`.
Evidence class: measured correctness-only single-route diagnostic.

The stock-reference and handoff arms used decode token 2167, experts
`[1, 13, 17, 21]`, and `ffn_moe_weights_softmax-0`. Both early stops returned
0 and explicitly rolled back KV state. Captured activation was bitwise equal.

For h=2 and h=3, serial-vs-stock and async-vs-stock relative maximum error was
`5.60445568e-08`, cosine was 1.0, and async-vs-serial was bitwise equal. The
frozen decision is `LIVE_MOE_HANDOFF_EXACTNESS_GO`.

Focused validation passed 61 tests; the full model-free suite passed 258.
Native build, runtime provenance and resource gates passed. Runtime resources
recorded zero failed GPU samples and zero process swap.

This admits a separately frozen timing protocol for this live boundary. It
does not establish timing, output reinjection, committed-token continuation,
full-model performance, prefetch, or physical traffic.
