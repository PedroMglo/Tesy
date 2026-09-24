# Mixed-residency Stage B protocol

Date: 2026-09-24  
Branch: `research/mixed-residency-stage-b-20260924`  
Classification: prospective isolated mixed-FFN diagnostic

## Motivation

Stage A reproduced the admitted 4 GiB LRU expert hit rate and grouped routed
top-4 calls by the number of experts already resident in the hypothetical GPU
cache.

Frozen grouped result:

- h=0 GPU hits: 39 groups (10.833333%);
- h=1: 26 groups (7.222222%);
- h=2: 62 groups (17.222222%);
- h=3: 128 groups (35.555556%);
- h=4: 105 groups (29.166667%);
- 360 routed groups;
- 1,440 expert uses;
- aggregate hit rate 66.25%.

Versioned Stage A result:
`research/MIXED-RESIDENCY-GROUPED-REPLAY-RESULT-20260924.md`.

Admitted raw histogram SHA-256:
`ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

Stage B measures the isolated execution cost of every h=0..4 case so the
trace-weighted diagnostic does not interpolate the rarer h=0/h=1 cases.

## Real expert contract

Use layer 0 experts 0,1,2,3 from the locked gpt-oss-20b MXFP4 GGUF.

The same admitted native inventory contract applies:

- 32 experts/layer;
- 13,253,760 encoded bytes/expert;
- MXFP4 expert matrices `[2880,2880,32]`;
- F32 expert biases `[2880,32]`;
- final GGUF expert dimension must prove exact contiguous per-expert slices.

No synthetic weight matrices are allowed.

## FFN semantics

Reuse pinned ggml operators and the gpt-oss expert path:

- `ggml_mul_mat_id`;
- `ggml_add_id`;
- `ggml_swiglu_oai(alpha=1.702, limit=7.0)`;
- down projection;
- per-expert mixture multiplication;
- expert sum.

The router itself is not measured.

The deterministic top-4 expert IDs are `[0,1,2,3]`. Each expert receives a
global mixture coefficient of 0.25.

Uniform coefficients are a correctness/performance diagnostic choice; they are
not observed router probabilities.

## CPU/GPU authority

"CPU miss" means the expert FFN executes on the pinned CPU backend.

For MXFP4 expert weights, Stage B asks the CPU backend for its extra buffer
types and chooses the first buffer that the CPU device itself reports as
supporting `GGML_OP_MUL_MAT_ID` for compact expert counts 1..4. It then falls
back to the CPU default buffer. Biases use the CPU default F32 buffer.

This deliberately measures the mature CPU fallback available to a Tesy
mixed-residency design. It does not assume that the textual
`--n-cpu-moe` override name uniquely determines the loader's concrete storage
buffer: the pinned loader may consider host/extra/repack buffers when applying
a CPU override.

The selected CPU weight/bias buffer type names are recorded in the raw result.

GPU hits use the CUDA default buffer type.

All expert weights are populated into their assigned backend buffers before
timing. Stage B measures **resident execution only**; it does not time expert
weight movement.

## h cases

Measure all five cases:

- h=0: 0 GPU-resident + 4 CPU;
- h=1: 1 GPU + 3 CPU;
- h=2: 2 GPU + 2 CPU;
- h=3: 3 GPU + 1 CPU;
- h=4: 4 GPU + 0 CPU.

Source experts with the lowest IDs are assigned to GPU first. Shapes/types are
identical across experts, so this is a deterministic hit-count diagnostic, not
an expert-identity/routing-distribution experiment.

Measurement order is frozen:

`0,4,1,3,2`

The serialized result is sorted by h=0..4.

## Direct serial path

For each h with CPU misses:

1. the input activation begins on GPU;
2. copy the 2880-F32 activation GPU -> CPU;
3. execute the CPU subset;
4. execute the resident GPU subset when h>0;
5. copy the CPU partial 2880-F32 output CPU -> GPU;
6. aggregate CPU and GPU partials on GPU.

For h=0, the all-CPU result is copied to GPU.

For h=4, no activation leaves GPU.

No CPU/GPU concurrency is used in this first measurement. The direct wall time
therefore includes partition/materialization overhead and is an intentionally
serial correctness/performance gate.

## Numerical reference

Before timing, compute an all-CPU top-4 reference with the same:

- real expert tensors;
- deterministic input;
- experts 0..3;
- global 0.25 weights.

Every h case must produce finite output and satisfy:

- relative max error <= 0.005, normalized by `max(1,max_abs_ref)`;
- cosine similarity >= 0.9999.

Any mismatch terminates and preserves the campaign.

This is isolated FFN numerical parity, not bitwise equality or token equality.

## Samples

Frozen settings:

- layer 0;
- 12 CPU threads;
- 3 warmups/case;
- 21 samples/case;
- 5 inner executions/sample.

Record every sample plus median, p95, min, max and mean.

The first campaign is diagnostic, not a tail-latency or stable-ranking claim.

## Trace-weighted diagnostic

After all h cases PASS, combine their measured median wall times with the
admitted Stage A grouped counts:

`weighted_ms = sum(groups_h * median_h) / 360`.

Compare this arithmetic diagnostic to the measured h=0 median from the same
campaign.

This combines measured isolated case medians with a trace-derived residency
opportunity distribution. It is not a measured cache/full-model runtime.

## Build/provenance

Dedicated build:

- exact pinned llama.cpp;
- Release;
- GCC/G++ 15;
- CUDA compiler `/usr/local/cuda/bin/nvcc`;
- CUDA architecture 89;
- `GGML_CUDA=ON`;
- `GGML_BACKEND_DL=OFF`.

The timed campaign records:

- clean Tesy HEAD;
- clean llama.cpp HEAD;
- locked model verification;
- physical reference-host identity;
- no competing GPU compute process;
- CMake identity;
- tool SHA-256;
- selected `libggml-cuda.so` SHA-256;
- exact live executable/argv;
- exact mapped selected `libggml-cuda.so`;
- complete process/GPU resource telemetry.

The Stage A histogram must match the frozen SHA-256 and exact grouped counts
before the GPU benchmark starts.

## Resource stop rules

Stop and preserve FAIL on:

- histogram identity/content mismatch;
- source/model/host/build provenance mismatch;
- competing GPU process;
- live executable/argv/CUDA-backend mismatch;
- numerical parity failure;
- non-finite output/timing;
- incomplete GPU telemetry;
- process swap;
- sampled free GPU memory < 1024 MiB;
- sampled MemAvailable < 2048 MiB;
- corrupted/missing result.

Never reuse a failed output root.

## Operator flow

Build separately:

```bash
bash scripts/bootstrap_mixed_residency.sh
```

Then:

```bash
campaign="results/mixed-residency-stage-b-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_mixed_residency_stage_b.sh \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  results/mixed-residency-opportunity-20260924T105132Z/histogram.json \
  "$campaign"
```

If the local 105132Z histogram is byte-identical to the admitted Stage A raw
artifact, it passes the SHA gate. Otherwise the campaign stops before any GPU
work and the mismatch must be investigated.

## Decision after Stage B

Promote mixed residency only if:

- h=2 and h=3 preserve meaningful measured latency improvement over h=0;
- h=4 remains a resident-GPU anchor;
- trace-weighted arithmetic headroom remains positive after measured
  partition/aggregation overhead.

If the mixed cases collapse the arithmetic headroom, kill this execution
boundary before implementing concurrency or prefetch.

If the serial mixed cases retain material headroom, the next discriminant is
CPU/GPU overlap. Prefetch remains after that and must include wasted-prefetch
accounting.

## Claim boundary

This experiment measures isolated serial top-4 mixed CPU/GPU expert FFN
execution with real resident weights. It does not measure expert-weight
transfer, cache lookup, prefetch, router cost, concurrent CPU/GPU execution,
full-model throughput, >RAM execution or physical PCIe/DRAM/NVMe traffic.
