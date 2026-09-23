# Implementation status

Cut: 2026-09-23, branch `fix/n3-trace-evidence-and-byte-inventory-20260923`.

| Capability | Status | Evidence boundary |
|---|---|---|
| Broad Tesy novelty | NO-GO | prior art overlaps generic MoE caching/offload/speculation |
| Narrow opportunity discovery | OPEN | must emerge from measured gaps, not wording |
| llama.cpp stock source pin | IMPLEMENTED | exact source commit frozen |
| KTransformers reference pin | IMPLEMENTED | comparator/reference only |
| vLLM reference role/pin | IMPLEMENTED | B4 comparator; not initial 8 GiB backend |
| model lock + verifier | IMPLEMENTED | gpt-oss-20b exact SHA and byte count frozen |
| host doctor | IMPLEMENTED / HOST_NOT_RUN_HERE | physical laptop not visible through GitHub connector |
| stock B0 smoke harness | IMPLEMENTED_SOURCE | physical model run pending |
| passive native MoE tracer | BUILD_VALIDATED_CPU_BASE / PATCH_PENDING_PR_CI | foundation tracer built in CI; evidence fixes need current-branch CI |
| trace token-ID OFF/ON gate | CORRECTED_SOURCE / NOT_RUN_MODEL_REQUIRED | `--tokens-out` now actually publishes no-replace evidence |
| native trace parser/headroom | IMPLEMENTED | expert-count space only |
| GGUF expert-byte inventory | IMPLEMENTED_SOURCE | locked real GGUF not inspected yet |
| native trace -> encoded-byte normalization | IMPLEMENTED_SOURCE | one-token graphs only |
| RAM/VRAM cache simulator | IMPLEMENTED | simulated encoded bytes, not physical traffic |
| Python tests | FOUNDATION_CI_PASS / CURRENT_PATCH_CI_PENDING | 3.11/3.12/3.13 foundation passed |
| CUDA/reference-laptop build | NOT_RUN_HOST_REQUIRED | RTX 4060 physical host required |
| gpt-oss-20b load/chat | NOT_RUN_MODEL_REQUIRED | user-managed download required |
| physical NVMe/PCIe expert traffic | NOT_IMPLEMENTED | encoded footprints are not physical counters |
| native Tesy expert cache | NOT_IMPLEMENTED_BY_DESIGN | blocked on baseline/trace evidence |
| causal prefetch | NOT_IMPLEMENTED | blocked on headroom evidence |
| speculative K>1 | NOT_IMPLEMENTED | blocked on K=1 evidence |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only, do not download yet |

No status above implies an end-to-end Tesy speedup.
