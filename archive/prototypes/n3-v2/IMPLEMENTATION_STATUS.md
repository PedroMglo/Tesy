# Implementation status

Cut: 2026-09-23.

| Capability | Status | Evidence boundary |
|---|---|---|
| Broad architecture novelty | NO-GO | prior art overlaps generic MoE offload/cache/prefetch/speculation |
| Narrow future contribution | OPEN / UNKNOWN | must arise from measured gap |
| model lock + SHA/byte verifier | IMPLEMENTED | locked gpt-oss-20b identity fixed; local bytes not yet observed here |
| host doctor/capacity planner | IMPLEMENTED | physical laptop NOT_RUN in GitHub-only session |
| stock llama.cpp pin | PINNED | foundation CI passed source/build boundary; physical CUDA build pending |
| KTransformers reference | PINNED_REFERENCE | no reference-host execution yet |
| vLLM reference | PINNED_REFERENCE_B4 | relevant MoE/offload prior art; not initial 8 GiB backend |
| B0 stock smoke harness | IMPLEMENTED_SOURCE | real model NOT_RUN |
| native ffn_moe_topk tracer | BUILD_VALIDATED_BASE / CURRENT_FIX_CI_PENDING | base tracer compiled in GitHub CI; fail-closed/CPU-MoE delta awaits this PR CI |
| paired token-ID trace gate | CORRECTED_SOURCE | real-model OFF/ON comparison NOT_RUN |
| count-space trace/headroom | IMPLEMENTED | trace-derived expert counts only |
| encoded expert-byte inventory | IMPLEMENTED_SOURCE | real GGUF inventory NOT_RUN |
| native trace -> byte trace normalization | IMPLEMENTED_SOURCE | one-token decode graphs; bytes are GGUF encoded footprint |
| RAM/VRAM cache simulator | IMPLEMENTED | simulated encoded bytes, not physical traffic |
| physical NVMe/PCIe expert traffic | NOT_IMPLEMENTED | no physical-byte claim allowed |
| Tesy custom expert cache | NOT_IMPLEMENTED_BY_DESIGN | blocked on baselines/headroom |
| causal prefetch | NOT_IMPLEMENTED | blocked on measured headroom |
| speculative K>1 | NOT_IMPLEMENTED | blocked on K=1 evidence |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only; do not download yet |

No row establishes a Tesy speedup or real-model PASS.
