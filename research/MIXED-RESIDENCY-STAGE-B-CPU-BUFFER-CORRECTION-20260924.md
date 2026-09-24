# Stage B CPU-buffer authority audit resolution

Date: 2026-09-24  
Campaign: `results/mixed-residency-stage-b-20260924T125101Z`  
Campaign base commit: `086d234651596ed1e0bb492a2e7e5daf19d36596`  
Result commit: `8dec61cb1f5ffd719b1eef20f30fbaea3e5a638c`

## Audit question

After the first Stage B result, source review of pinned llama.cpp established
that a textual CPU override does not by itself prove the concrete storage buffer
selected by the model loader: CPU extra/repack candidates may be considered
before literal CPU default.

The question was therefore whether the Stage B binary that actually ran had
hard-coded `CPU`, or whether it had already used the prospective CPU-backend
extra/repack-aware selector.

## Reproduced source state

The campaign records base commit:

`086d234651596ed1e0bb492a2e7e5daf19d36596`.

At that exact commit, `native/tesy_mixed_residency.cpp` already contained
`select_cpu_compute_weight_buft()`.

That function:

1. queries `ggml_backend_dev_get_extra_bufts` from the pinned CPU backend;
2. tests each candidate with the CPU device's
   `ggml_backend_dev_supports_op(..., MUL_MAT_ID)`;
3. requires support for compact expert counts 1,2,3,4;
4. falls back to the CPU default buffer only if earlier CPU extra/repack
   candidates do not satisfy that contract.

The exact campaign raw result serialized:

- `cpu_weight_buffer_type = CPU`;
- `cpu_bias_buffer_type = CPU`.

Therefore the observed `CPU` weight buffer was **selected by the frozen
extra/repack-aware Stage B selector**, not forced by a stale hard-code.

## Consequence

The Stage B campaign does **not** require a rerun for CPU extra/repack
selection.

The measured results remain admitted for the frozen Tesy mixed-residency
boundary:

- h=0: 0.760742 ms;
- h=1: 0.684444 ms;
- h=2: 0.631912 ms;
- h=3: 0.654776 ms;
- h=4: 0.268824 ms;
- trace-weighted diagnostic: 0.551891 ms;
- speedup-equivalent vs h=0: 1.378427x;
- parity PASS in all five cases;
- zero process swap;
- complete sampled GPU telemetry.

## Loader-vs-microbenchmark boundary

This audit does **not** claim that the model loader would necessarily choose the
same concrete buffer for every `--n-cpu-moe` tensor. The loader's
`buft_list_cpu` can include additional candidate classes such as GPU host
buffers.

Stage B asks a narrower architectural question: given a miss executed by the
CPU backend, what is the cost using the CPU backend's own compatible
extra/repack candidates with default fallback?

For that frozen boundary on this host and shape, the selector chose `CPU`.

## Decision

Stage B is admitted as a reference-host diagnostic.

The next discriminating gate is CPU/GPU overlap for the material mixed cases,
not a repeat of the serial Stage B campaign.

Prefetch remains later and still requires wasted-prefetch accounting.

## Claim boundary

This audit resolves the CPU-buffer-selection provenance of the already executed
Stage B microbenchmark. It does not promote the result to full-model speedup,
cache behavior, or physical PCIe/DRAM/NVMe traffic.
