# Implementation status — 2026-09-23

Classification: DEVELOPMENT_ONLY. No end-to-end Tesy performance qualification.

| Component | Implemented | Validation in this task |
|---|---|---|
| Strict JSON, file identity, atomic no-replace JSON | yes | CPU tests, race and mutation faults |
| GGUF v3 LE bounded inventory | yes | generated fixtures, truncation/type/overlap faults |
| Model hash/size verification and download plan | yes | metadata and synthetic negative tests |
| Read-only host doctor | yes | executed on development container, not laptop |
| LRU/LFU/causal-transition two-cache replay | yes | hand oracle, exhaustive 243 sequences, 300 random variable-size cases |
| Target-route union analysis | yes | synthetic only, NO acceptance inferred |
| Per-tier transport bound | yes | assumed/measured/upper-bound distinctions tested |
| Native F32 demand cache + SwiGLU expert | yes | release build, ASan/UBSan, synthetic read/eviction/pin/fault tests |
| Stock llama.cpp chat command/supervisor | yes | command/resource tests; REAL_MODEL_NOT_RUN |
| Locked llama.cpp external source/CUDA build | script | NOT_RUN_NETWORK_AND_CUDA_REQUIRED |
| Live routing trace collector for quantized LLM | no | NEXT_GATE |
| Native cache integrated with quantized GGUF experts | no | NEXT_GATE |
| CUDA expert cache/prefetch implementation | no | design pending live traces |
| Online joint speculation/residency controller | no | novelty and usefulness UNESTABLISHED |
| Optimized Tesy chat/serve | no | stock launcher is not a substitute |
| Real-model exactness, benchmarks, sustained stability | no | NOT_RUN_MODEL_AND_HOST_REQUIRED |

## Model support matrix

| Model/quantization | Metadata | Stock handoff | Optimized native Tesy |
|---|---|---|---|
| Qwen3-30B-A3B-Instruct-2507 Q4_K_M | upstream/artefact identity recorded; local fixture parser tested | implementation present, actual file/model NOT_RUN | NOT_IMPLEMENTED |
| Compact synthetic F32 experts (not an LLM) | fixture | not applicable | CPU primitive SYNTHETIC_VALIDATED |
| gpt-oss/Qwen3.5/other MoE families | not admitted in this phase | no validated profile | NOT_IMPLEMENTED |

The GGUF parser rejects unknown quantization sizes and split files; it does not
infer support. The stock launcher only accepts the initial qwen3moe profile.
Do not mark a model validated based on its advertised model-card support.
