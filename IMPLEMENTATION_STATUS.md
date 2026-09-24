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
| byte-weighted native trace simulation | REAL_TRACE_DERIVED_SIMULATION | 16 GiB/4 GiB hypothetical two-tier LRU over the native-relocked equal-size inventory; not physical traffic |
| reference bring-up pipeline | PASS_DIAGNOSTIC_REFERENCE_HOST | third campaign completed after two preserved failed/aborted attempts; details in `research/results/first-real-bringup-20260923/RESULT.md` |
| stock llama.cpp real gpt-oss-20b load | PASS_DIAGNOSTIC_STOCK_SMOKE | 16-token stock generation; no chat or benchmark qualification |
| stock B0/B1 measurements | INCONCLUSIVE_RERUN_REQUIRED | physical-host runs exist, but review invalidated same-work admission: placement telemetry empty, provenance incomplete and token trajectories unretained |
| original n-cpu-moe + auto-fit sweep | STATIC_NO_GO_PIN_FIT_CONFLICT | pinned source reproduces incompatible tensor override / fit semantics; preserved N=4 campaign OOM is not a capacity bound |
| capacity-gated stock placement frontier | INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN | historical campaign retains projected N=12/16/20/24 vs N=0/4/8 sets, but publication admissions were withdrawn because virtualization/physical-host state was not proven; new campaign identity required |
| pinned llama-fit-params utility | PASS_REFERENCE_HOST | built from pinned llama.cpp on reference host; binary/toolchain identity retained in published capacity provenance |
| llama.cpp build provenance lock | PASS_REFERENCE_HOST | capacity campaign verified frozen CMake/GCC/CUDA/server/libggml-cuda identity with zero mismatches |
| live backend mapping provenance | IMPLEMENTED_MODEL_FREE_HOST_RETRY_REQUIRED | revised pilot binds frozen argv to `/proc/<pid>/cmdline`, executable and mapped pre-hashed libggml-cuda; two physical attempts stopped before this check, so revised live provenance remains NOT_RUN |
| realized stock placement telemetry | CUDA0_PARITY_OBSERVED_REVISED_GATE_RETRY_REQUIRED | Attempt 2 physically observed CUDA0 6095.35 MiB versus 6095 MiB projected; the Host equality gate was invalidated because `CPU_Mapped` is an mmap span, not fit-print logical Host bytes. Telemetry v2 requires positive Host mmap buffer presence and classifies its span `NOT_COMPARABLE_MMAP_SPAN`; revised live gate remains NOT_RUN |
| capacity result publication | INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN | raw fitter evidence remains preserved/hash-manifested; publication layer has empty admitted/rejected sets and requires a new PHYSICAL-host-verified capacity campaign |
| stock placement timing pilot | BLOCKED_CAPACITY_REVALIDATION_REQUIRED | two historical pre-request failures remain preserved; revised runner is fail-closed on the withdrawn capacity publication. No new timing pilot is authorized until a fresh capacity-only campaign proves PHYSICAL host and publishes a new admitted set prospectively |
| stock B2 gpt-oss lazy-expert baseline | STATIC_NO_GO | pinned gpt-oss expert tensors are not marked `TENSOR_READ_LAZY`; no model-bearing B2 run is justified for this purpose |
| KTransformers baseline | PINNED_NOT_REPRODUCED | reproduce only if compatible with selected model/host |
| vLLM baseline | PINNED_NOT_REPRODUCED | B4 only if 8 GiB/32 GiB envelope admits it |
| native Tesy expert residency/cache | NOT_IMPLEMENTED | forbidden until baseline + trace/headroom establish a concrete gap |
| CPU-vs-transfer-vs-GPU expert crossover | UNBLOCKED_DESIGN_REQUIRED | native inventory PASS provides admitted real shapes/types; next gate should measure CPU-resident expert path, requested Host->GPU weight transfer and resident-GPU compute separately, without physical-PCIe claims |
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
