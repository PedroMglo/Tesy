# Mixed-residency CPU/GPU overlap-bound protocol

Date: 2026-09-24  
Branch: `research/mixed-residency-overlap-bound-20260924`  
Classification: prospective component diagnostic; no async execution

## Motivation

The admitted serial Stage B campaign measured real top-4 mixed-residency FFN
execution with parity PASS:

- h=0: 0.760742 ms;
- h=1: 0.684444 ms;
- h=2: 0.631912 ms;
- h=3: 0.654776 ms;
- h=4: 0.268824 ms.

The trace-weighted diagnostic was 0.551891 ms, 1.378x relative to h=0.

The exact Stage B base commit already contained the frozen CPU-backend
extra/repack-aware selector and the raw result recorded
`cpu_weight_buffer_type=CPU`. No buffer-selection rerun is required.

However, h=3 was slower than h=2. Therefore hit count alone is not a sufficient
latency model and actual CPU/GPU concurrency should not be implemented before
measuring which branch dominates each mixed case.

## Scope

Reuse the exact Stage B real-weight top-4 contract:

- layer 0;
- experts 0,1,2,3;
- 32 experts/layer;
- 13,253,760 encoded bytes/expert;
- MXFP4 matrices `[2880,2880,32]`;
- F32 biases `[2880,32]`;
- uniform global expert mixture weights 0.25;
- pinned ggml gate/up/down + bias + SwiGLU OAI semantics;
- CPU-backend extra/repack-aware weight-buffer selection;
- CUDA default GPU buffer.

No router, cache lookup, prefetch or weight transfer is measured.

## Direct serial path

For h=1..3 the admitted serial path is:

1. GPU -> CPU input activation copy;
2. CPU subset compute;
3. GPU subset compute;
4. CPU partial output -> GPU copy;
5. GPU aggregation.

h=0 and h=4 remain all-CPU/all-GPU anchors.

The direct wall measurement is retained exactly as a serial baseline.

## Component measurements

After the direct serial timing and numerical parity gate, measure separately:

- `activation_d2h`;
- `cpu_compute`;
- `gpu_compute`;
- `cpu_partial_h2d`;
- `gpu_aggregation`.

Component timing occurs outside the direct-wall timing.

Every component uses completion wall time with explicit backend
synchronization.

The component measurements are diagnostics and need not sum exactly to the
direct-wall median because they are sampled separately.

## Post-D2H overlap bound

The first concurrency design considered is deliberately narrow:

1. complete input D2H;
2. overlap CPU subset compute with GPU subset compute;
3. complete CPU-partial H2D;
4. aggregate on GPU.

Therefore, for h=1..3:

`BOUND = D2H + max(CPU_COMPUTE, GPU_COMPUTE) + H2D + AGGREGATION`.

For h=0/h=4, the bound collapses to the sole CPU/GPU path.

This is not a hardware lower bound on every possible scheduling design. It is
the prospective bound for the specific concurrency mechanism we would
implement next.

## Numerical contract

The same Stage B all-CPU top-4 numerical reference and thresholds remain:

- finite outputs;
- normalized max error <= 0.005;
- cosine similarity >= 0.9999.

Any mismatch terminates the campaign.

## Measurement order and samples

Freeze:

- case order `0,4,1,3,2`;
- 12 CPU threads;
- 3 warmups;
- 21 samples;
- 5 inner repetitions/sample.

Record direct and component raw sample vectors plus median/p95/min/max/mean.

## Grouped trace weighting

Use only the admitted Stage A histogram:

- h=0: 39;
- h=1: 26;
- h=2: 62;
- h=3: 128;
- h=4: 105;
- total 360 groups.

Raw histogram SHA-256:

`ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

Calculate:

- trace-weighted direct median diagnostic;
- trace-weighted post-D2H overlap-bound diagnostic;
- bound speedup relative to weighted direct.

These are arithmetic diagnostics, not measured cache/full-model latency.

## Prospective decision threshold

Implement actual async CPU/GPU overlap only if:

1. all h cases PASS numerical/resource/provenance gates;
2. h=2 and h=3 remain finite and correctly decomposed;
3. trace-weighted overlap bound is at least **10% lower** than the
   trace-weighted direct diagnostic:

`weighted_bound <= 0.90 * weighted_direct`.

Classification:

- threshold met: `OVERLAP_IMPLEMENTATION_GO`;
- threshold not met: `OVERLAP_COMPLEXITY_NO_GO`.

The 10% threshold is an engineering gate for adding concurrency complexity,
not a universal performance significance threshold.

## Provenance/resource gates

Reuse the Stage B fail-closed runner boundaries:

- exact clean Tesy/llama.cpp provenance;
- locked model/reference host;
- no competing GPU compute process;
- frozen CMake/CUDA build;
- exact executable/argv/mapped `libggml-cuda.so`;
- admitted histogram identity;
- zero process swap;
- complete GPU telemetry;
- >=1024 MiB sampled GPU free headroom;
- >=2048 MiB sampled MemAvailable.

Never reuse a failed campaign root.

## No async implementation in this gate

This branch must not call `ggml_backend_graph_compute_async`, create worker
threads for CPU/GPU overlap, or otherwise measure concurrency.

The purpose is to decide whether writing that mechanism is justified.

## Claim boundary

This experiment measures isolated serial mixed-FFN components and derives a
specific post-D2H compute-overlap bound. It does not measure actual concurrent
CPU/GPU execution, cache behavior, prefetch, full-model throughput, physical
PCIe/DRAM/NVMe traffic, >RAM execution or Tesy speedup.
