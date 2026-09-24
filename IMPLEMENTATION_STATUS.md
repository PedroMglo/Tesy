# Implementation status

Date: 2026-09-23

This table distinguishes source implementation, model-free CI validation and
reference-host/model validation. No source-only row is a performance claim.

| Capability | Status | Evidence boundary |
|---|---|---|
| N0 prior-art screen | IMPLEMENTED | second pass records `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`; not a patent/legal opinion |
| backend source locks | PINNED_LLAMA_BUILT_REFERENCE_HOST | llama.cpp pin built with CUDA 13.3/GCC 15 on physical host; other backends remain pinned comparators |
| vLLM role | COMPARATOR_B4 | source/docs reviewed and pinned; NOT_INSTALLED_REFERENCE_HOST |
| model lock + SHA verifier | REAL_MODEL_VERIFIED | locked gpt-oss-20b GGUF byte size and SHA-256 PASS on reference host |
| reference-host identity check | PASS_REFERENCE_HOST | physical HX370/RTX4060/32 GiB laptop identity PASS in first real bring-up |
| host doctor | MEASURED_REFERENCE_HOST | RAM/swap, GPU/driver, CUDA toolkit, NVMe mount and competing processes captured at campaign start |
| capacity planner | IMPLEMENTED_MODEL_FREE | static admission only; >RAM stays INCONCLUSIVE without validated loader |
| normalized routing schema | IMPLEMENTED_MODEL_FREE | strict JSONL parser |
| native llama.cpp MoE top-k tracer | REAL_MODEL_DIAGNOSTIC_PASS | pinned CUDA build and 384 routing records from real GGUF; zero weight layers offloaded in paired gate |
| paired trace OFF/ON token gate | REAL_MODEL_TOKEN_ID_EQUALITY_PASS | same 16 generated IDs for one deterministic raw prompt; no bitwise/numerical parity claim |
| count-space LRU headroom | REAL_TRACE_DERIVED | 1,440 one-token expert accesses; equal-sized-slot LRU, not physical bytes |
| Belady offline oracle | REAL_TRACE_DERIVED | non-causal equal-slot lower bound; not a production policy |
| GGUF expert payload inventory | INCONCLUSIVE_DEPENDENCY_LOCK_REQUIRED | diagnostic inventory retained, but transitive Python dependencies were not frozen prospectively |
| byte-weighted native trace simulation | NOT_ADMITTED_DEPENDENCY_LOCK_REQUIRED | exploratory output retained; depends on non-confirmatory inventory and is not physical traffic |
| reference bring-up pipeline | PASS_DIAGNOSTIC_REFERENCE_HOST | third campaign completed after two preserved failed/aborted attempts; details in `research/results/first-real-bringup-20260923/RESULT.md` |
| stock llama.cpp real gpt-oss-20b load | PASS_DIAGNOSTIC_STOCK_SMOKE | 16-token stock generation; no chat or benchmark qualification |
| stock B0/B1 measurements | INCONCLUSIVE_RERUN_REQUIRED | physical-host runs exist, but review invalidated same-work admission: placement telemetry empty, provenance incomplete and token trajectories unretained |
| original n-cpu-moe + auto-fit sweep | STATIC_NO_GO_PIN_FIT_CONFLICT | pinned source reproduces incompatible tensor override / fit semantics; preserved N=4 campaign OOM is not a capacity bound |
| capacity-gated stock placement frontier | HOST_ATTEMPT_FAILED_INSTRUMENTATION_RETRY_REQUIRED | first physical capacity-only attempt stopped before estimator because backend feature probe used llama-server for a llama-cli feature lock; source/model/host checks passed, runner corrected, retry pending current-head CI |
| pinned llama-fit-params utility | SOURCE_REQUIRED_BUILD_TARGET_ADDED | bootstrap target added; reference-host binary rebuild remains NOT_RUN |
| llama.cpp build provenance lock | IMPLEMENTED_MODEL_FREE | strict CMake/compiler/CUDA/server/libggml-cuda identity gate; reference-host replay remains NOT_RUN |
| live backend mapping provenance | IMPLEMENTED_MODEL_FREE | timed runs verify process executable and mapped pre-hashed libggml-cuda; timing campaign remains NOT_RUN |
| capacity result publication | IMPLEMENTED_MODEL_FREE | capacity-only artifacts are validated, bounded, no-replace and hash-manifested before Git staging |
| stock B2 gpt-oss lazy-expert baseline | STATIC_NO_GO | pinned gpt-oss expert tensors are not marked `TENSOR_READ_LAZY`; no model-bearing B2 run is justified for this purpose |
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
