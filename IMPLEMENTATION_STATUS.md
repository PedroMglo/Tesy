# Implementation status

Date: 2026-09-24

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
| GGUF expert payload inventory | NATIVE_GGUF_PASS_DERIVATION_REFERENCE_HOST | metadata-only native helper PASS on reference laptop: 24 layers × 32 experts, 13,253,760 encoded bytes/expert, types f32+mxfp4, shapes [2880,32] and [2880,2880,32]; not physical fetch granularity |
| byte-weighted native trace simulation | ADMITTED_NATIVE_INVENTORY_REPLAY_PASS | 16 GiB/4 GiB replay with admitted native inventory: 4 GiB LRU hit 66.25%, Belady(324) 70.21%; trace-derived encoded-payload simulation, not physical traffic |
| reference bring-up pipeline | PASS_DIAGNOSTIC_REFERENCE_HOST | third campaign completed after two preserved failed/aborted attempts; details in `research/results/first-real-bringup-20260923/RESULT.md` |
| stock llama.cpp real gpt-oss-20b load | PASS_DIAGNOSTIC_STOCK_SMOKE | 16-token stock generation; no chat or benchmark qualification |
| stock B0/B1 measurements | INCONCLUSIVE_RERUN_REQUIRED | physical-host runs exist, but review invalidated same-work admission: placement telemetry empty, provenance incomplete and token trajectories unretained |
| original n-cpu-moe + auto-fit sweep | STATIC_NO_GO_PIN_FIT_CONFLICT | pinned source reproduces incompatible tensor override / fit semantics; preserved N=4 campaign OOM is not a capacity bound |
| capacity-gated stock placement frontier | SOURCE_BACKED_CAPACITY_GATE_PASS_REFERENCE_HOST | published campaign `n-cpu-moe-capacity-20260923T233416Z`: N=12/16/20/24 admitted, N=0/4/8 rejected by projected GPU headroom; estimator-derived, not measured runtime memory |
| pinned llama-fit-params utility | PASS_REFERENCE_HOST | built from pinned llama.cpp on reference host; binary/toolchain identity retained in published capacity provenance |
| llama.cpp build provenance lock | PASS_REFERENCE_HOST | capacity campaign verified frozen CMake/GCC/CUDA/server/libggml-cuda identity with zero mismatches |
| live backend mapping provenance | PASS_REFERENCE_HOST_TIMING_PILOT | successful three-point pilot verified exact live argv, process executable and mapped pre-hashed libggml-cuda for every observation |
| realized stock placement telemetry | PASS_REFERENCE_HOST_TIMING_PILOT | telemetry v2 PASS for auto-fit/N12/N24: CUDA0 model-buffer parity within frozen tolerance, exact live argv PASS; Host mmap spans retained as `NOT_COMPARABLE_MMAP_SPAN`, not logical Host bytes or resident DRAM |
| capacity result publication | PASS_DERIVED_PUBLICATION | capacity result published at commit `5a8bbf08eb95069b1847f724e5d1be98c6392678`; raw fitter evidence retained byte-identical and hash-manifested |
| stock placement timing pilot | PASS_SINGLE_OBSERVATION_DIAGNOSTIC | successful campaign `n-cpu-moe-timing-pilot-20260924T003640Z`: auto-fit/N12/N24 exact 64-token trajectory, zero swap, complete GPU telemetry and provenance PASS; auto-fit and N12 show no gross separation in one observation, while N24 trades ~4.74 GiB lower peak VRAM for large prompt/decode/TTFT penalty; no stable ranking claim |
| manual N12/N16/N20/N24 continuum shape gate | PASS_SINGLE_OBSERVATION_DIAGNOSTIC | campaign `n-cpu-moe-continuum-shape-20260924T083136Z`: four fresh processes, exact 64-token greedy trajectory equality, provenance/placement/resource gates PASS and zero swap; N12→N24 peak VRAM -4.74 GiB with decode -27.51%; no stable knee, ranking or Pareto claim |
| stock B2 gpt-oss lazy-expert baseline | STATIC_NO_GO | pinned gpt-oss expert tensors are not marked `TENSOR_READ_LAZY`; no model-bearing B2 run is justified for this purpose |
| KTransformers baseline | PINNED_NOT_REPRODUCED | reproduce only if compatible with selected model/host |
| vLLM baseline | PINNED_NOT_REPRODUCED | B4 only if 8 GiB/32 GiB envelope admits it |
| native Tesy expert residency/cache | NOT_IMPLEMENTED | forbidden until baseline + trace/headroom establish a concrete gap |
| CPU-vs-transfer-vs-GPU expert crossover | PASS_CPU_DEFAULT_REFERENCE_HOST_DIAGNOSTIC | campaign `expert-crossover-20260924T101753Z`: real-shape k=1/k=4 parity/resource gates PASS; pinned cold-GPU miss is ~3.05x/~3.64x slower than the measured CPU-default fallback while resident GPU is ~5.80x/~4.92x faster; post-run source audit shows loader CPU overrides may select extra/repack buffers, so CPU-default is a conservative comparator rather than unique loader-path authority |
| mixed GPU-hit / CPU-miss expert execution | STAGE_B_PASS_REFERENCE_HOST_DIAGNOSTIC | campaign `mixed-residency-stage-b-20260924T125101Z` PASS: h=0..4 parity, weighted diagnostic 0.551891 ms / 1.378x vs h=0, zero swap and complete GPU telemetry; audit of exact base `086d234` confirms the extra/repack-aware CPU-backend selector already ran and selected CPU, so next gate is CPU/GPU overlap |
| causal prefetch | NOT_IMPLEMENTED | only after locality/headroom and wasted-prefetch analysis |
| speculative K=2 | NOT_IMPLEMENTED | only after K=1 target/runtime correctness |
| joint K/residency scheduler | OPEN_RESEARCH_QUESTION | broad novelty overlap exists; benefit and narrower novelty unknown |
| optimized Tesy chat | NOT_IMPLEMENTED | stock conversational correctness first |
| gpt-oss-120b execution | NOT_AUTHORIZED_BY_EVIDENCE | metadata-only; do not download/run yet |

## CI history boundary

A prior branch head `72c31eb26960a153520cbf10f4bc3e1bd4e2f621` passed
Python 3.11/3.12/3.13 plus native tracer compilation.

Later feature commits intentionally re-entered CI and exposed lint regressions;
those failures are retained in GitHub Actions rather than relabelled. The
current draft development head is validated locally; no full CI was triggered
for this protocol revision.

No row above implies REAL_MODEL_VALIDATED unless it explicitly says so.
