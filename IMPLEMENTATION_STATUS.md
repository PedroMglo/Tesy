# Implementation status

Date: 2026-09-23

This table distinguishes source implementation, model-free CI validation and
reference-host/model validation. No source-only row is a performance claim.

| Capability | Status | Evidence boundary |
|---|---|---|
| N0 prior-art screen | IMPLEMENTED | second pass records `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`; not a patent/legal opinion |
| backend source locks | PINNED | llama.cpp, KTransformers, vLLM and external cache reference pinned; only llama.cpp native build is exercised by CI |
| vLLM role | COMPARATOR_B4 | source/docs reviewed and pinned; NOT_INSTALLED_REFERENCE_HOST |
| model lock + SHA verifier | IMPLEMENTED | first gpt-oss-20b artifact locked; user-managed real download NOT_RUN_MODEL_REQUIRED |
| reference-host identity check | IMPLEMENTED_MODEL_FREE | physical laptop check NOT_RUN_HOST_REQUIRED |
| host doctor | IMPLEMENTED_MODEL_FREE | live physical host NOT_RUN in this GitHub-only session |
| capacity planner | IMPLEMENTED_MODEL_FREE | static admission only; >RAM stays INCONCLUSIVE without validated loader |
| normalized routing schema | IMPLEMENTED_MODEL_FREE | strict JSONL parser |
| native llama.cpp MoE top-k tracer | BUILD_VALIDATED_CPU_CI | compiled against exact pinned llama.cpp; real-model routing NOT_RUN_MODEL_REQUIRED |
| paired trace OFF/ON token gate | IMPLEMENTED_NOT_RUN_MODEL_REQUIRED | token artefact + no-replace/provenance runner implemented |
| count-space LRU headroom | IMPLEMENTED_MODEL_FREE | TRACE_DERIVED only when real trace exists |
| Belady offline oracle | IMPLEMENTED_MODEL_FREE | non-causal equal-slot lower bound; not a production policy |
| GGUF expert payload inventory | IMPLEMENTED_MODEL_FREE | exact encoded-payload derivation when layout is admissible; real GGUF NOT_RUN_MODEL_REQUIRED |
| byte-weighted native trace simulation | IMPLEMENTED_MODEL_FREE | hypothetical LRU movement from trace + encoded payload; never physical traffic |
| reference bring-up pipeline | IMPLEMENTED_NOT_RUN_HOST_REQUIRED | doctor -> pinned build -> stock smoke -> paired trace -> inventory |
| stock llama.cpp real gpt-oss-20b load | NOT_RUN_MODEL_REQUIRED | first model-bearing blocker |
| stock B0/B1/B2 measurements | NOT_RUN_HOST_REQUIRED | automatic placement, CPU-MoE and admissible lazy/on-demand modes remain to measure |
| KTransformers baseline | PINNED_NOT_REPRODUCED | reproduce only if compatible with selected model/host |
| vLLM baseline | PINNED_NOT_REPRODUCED | B4 only if 8 GiB/32 GiB envelope admits it |
| native Tesy expert residency/cache | NOT_IMPLEMENTED | forbidden until baseline + trace/headroom establish a concrete gap |
| CPU-vs-transfer-vs-GPU expert crossover | NOT_RUN_HOST_REQUIRED | requires physical host and real expert shapes |
| causal prefetch | NOT_IMPLEMENTED | only after locality/headroom and wasted-prefetch analysis |
| speculative K=2 | NOT_IMPLEMENTED | only after K=1 target/runtime correctness |
| joint K/residency scheduler | OPEN_RESEARCH_QUESTION | broad novelty overlap exists; benefit and narrower novelty unknown |
| optimized Tesy chat | NOT_IMPLEMENTED | stock conversational correctness first |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only; do not download/run yet |

## CI history boundary

A prior branch head `72c31eb26960a153520cbf10f4bc3e1bd4e2f621` passed
Python 3.11/3.12/3.13 plus native tracer compilation.

Later feature commits intentionally re-entered CI and exposed lint regressions;
those failures are retained in GitHub Actions rather than relabelled. The PR
checks are the authority for the current head.

No row above implies REAL_MODEL_VALIDATED unless it explicitly says so.
