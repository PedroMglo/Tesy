# Stage B CPU-buffer authority correction

Date: 2026-09-24  
Affected campaign: `results/mixed-residency-stage-b-20260924T125101Z`  
Campaign result commit: `8dec61cb1f5ffd719b1eef20f30fbaea3e5a638c`

## What remains measured

The first Stage B campaign remains valid for the exact binary that ran:

- h=0: 0.760742 ms;
- h=1: 0.684444 ms;
- h=2: 0.631912 ms;
- h=3: 0.654776 ms;
- h=4: 0.268824 ms;
- trace-weighted diagnostic: 0.551891 ms;
- weighted speedup-equivalent vs h=0: 1.378427x;
- numerical parity PASS for all five h cases;
- zero process swap;
- complete sampled GPU telemetry.

The raw result recorded both CPU weight and bias buffer types as `CPU`.

These measurements are not invalidated or relabelled.

## Source correction

Pinned `--n-cpu-moe` generates CPU tensor-buffer overrides with
`ggml_backend_cpu_buffer_type()`.

However, when the loader applies a CPU override it calls
`select_weight_buft(..., buft_list_cpu)`. With extra buffers enabled by
default, `buft_list_cpu` may contain compatible host and CPU extra/repack
buffer types before the literal CPU default.

Therefore the first Stage B campaign measured an explicit **CPU-default
comparator**, not the strongest available CPU-backend fallback and not a proof
of the concrete buffer the model loader would select for every overridden
expert tensor.

## Revised Stage B implementation

The current Stage B source asks the CPU backend for its extra buffer types and
selects the first buffer whose CPU device reports support for MXFP4
`MUL_MAT_ID` for compact expert counts 1..4, with CPU-default fallback.

Bias tensors remain on the CPU default F32 buffer.

The selected weight and bias buffer type names are serialized in the raw result
and propagated into the validated summary.

## Decision

Do **not** promote the first campaign's 1.378x trace-weighted diagnostic to the
next overlap gate yet.

Run a fresh Stage B campaign with the revised CPU-backend buffer selection.

- If mixed h=2/h=3 headroom survives materially, advance to CPU/GPU overlap.
- If optimized CPU fallback erases the mixed-residency headroom, stop before
  implementing concurrency or prefetch.

The first campaign stays as a measured CPU-default baseline for comparison.

## Claim boundary

This correction concerns CPU storage/compute-buffer authority only. It does not
change the previously measured GPU case timings, numerical parity, routing
histogram, or resource telemetry. No full-model speedup or physical
PCIe/DRAM/NVMe claim follows.
