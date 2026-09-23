# n-cpu-moe timing pilot protocol

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Capacity evidence commit: `5a8bbf08eb95069b1847f724e5d1be98c6392678`  
Capacity evidence: `research/results/n-cpu-moe-capacity-20260923T233416Z/`  
Classification: prospective diagnostic pilot

## Question

Before spending a balanced multi-point Pareto campaign, do three stock placements
show enough measured separation to justify it?

The pilot compares:

1. `auto-fit-frozen`: the exact explicit placement emitted by pinned
   `llama-fit-params` in the admitted capacity campaign;
2. `n-cpu-moe-12`: the highest-GPU manual point admitted by the source-backed
   capacity gate;
3. `n-cpu-moe-24`: the all-MoE-CPU manual endpoint.

This is intentionally not a full sweep.

## Why these three points

The admitted manual set was `N = 12, 16, 20, 24`; `N = 0, 4, 8` were
rejected for projected GPU headroom.

`N=12` and `N=24` bracket the admitted manual continuum.

The stock auto-fit placement is not equivalent to a single `N`: it keeps
`-ngl 25` and emits tensor overrides that move the block-12 FFN and a suffix
of later expert tensors to CPU. Therefore `auto-fit-frozen` versus `N=12`
tests placement topology, while `N=12` versus `N=24` tests the broad
VRAM/CPU-residency trade.

If these three points do not establish a useful diagnostic separation,
measuring `N=16` and `N=20` is not automatically justified.

## Frozen workload

Same locked model/backend/prompt as the capacity gate:

- context: 4096;
- parallel: 1;
- CPU threads / batch threads: 12 / 12;
- generated tokens: exactly 64;
- temperature: 0;
- top-k: 1;
- seed: 42;
- prompt cache disabled;
- server warmup disabled;
- fresh `llama-server` process for every point;
- `--fit off` for every timed observation.

One observation is made per placement. This is a pilot, not confirmatory
performance evidence.

## Pre-timing capacity recheck

The runner must re-run pinned `llama-fit-params --fit-print on` for all three
placements against the current measured campaign-start resources.

Guards remain:

- 1024 MiB GPU free-memory target;
- 2048 MiB host MemAvailable guard;
- 16 MiB rounding guard around integer-MiB estimator output.

If any of the three placements is not admitted under current resources, stop
before starting `llama-server`.

The published capacity result remains the authority for why these points were
selected; the live recheck is the authority for whether they may be loaded now.

## Provenance

Before timing:

- model verification PASS;
- reference-host identity PASS;
- no competing GPU compute process;
- clean Tesy and llama.cpp worktrees;
- pinned source feature probe through `llama-cli`;
- locked build/toolchain/server/`libggml-cuda.so` provenance PASS;
- capacity evidence commit must be an ancestor of the pilot HEAD;
- exact prompt hash and backend hashes recorded.

For every running server:

- verify `/proc/<pid>/exe`;
- verify the pre-hashed `libggml-cuda.so` is the CUDA backend actually mapped
  by the process.

## Exactness

The first successful observation establishes the 64-token trajectory.

Every later observation must have:

- exactly 64 generated token IDs;
- `timings.predicted_n == 64`;
- the exact same token-ID SHA-256.

Mismatch stops the pilot. This is greedy token equality only, not bitwise
tensor equality or sampling-distribution equivalence.

## Runtime resource gates

Every observation must have:

- valid GPU telemetry sufficient to establish a peak;
- process VmSwap == 0;
- observed free GPU memory at peak >= 1024 MiB;
- observed MemAvailable >= 2048 MiB;
- non-empty placement/load log excerpt;
- runtime backend provenance PASS.

Violation stops and preserves the campaign.

## Output

Per placement:

- explicit command;
- capacity recheck stdout/stderr/parsed JSON;
- server-ready wall time;
- request TTFT/wall time;
- prompt and decode timings;
- exact token IDs/hash;
- peak observed GPU memory;
- minimum observed GPU free memory;
- process RSS/swap;
- minimum MemAvailable/SwapFree;
- temperature/power samples;
- placement excerpt;
- live runtime provenance.

Aggregate into `pilot-summary.json`.

No Pareto frontier is claimed from one observation per point.

## Interpretation gate

This pilot answers whether a larger campaign is worth buying.

After measurement:

- if correctness or resource gates fail, debug that failure under a new
  campaign identity;
- if the three observations are effectively too close or internally surprising,
  repeat/diagnose rather than filling in `N=16/20` automatically;
- if the measured endpoints expose a meaningful trade-off, then freeze the
  smallest confirmatory set prospectively.

No performance threshold or winner is preregistered.

## Claim boundary

This is stock llama.cpp placement calibration on one model/workload/host.

It does not measure physical PCIe/NVMe expert traffic, prove a Tesy cache or
prefetch benefit, validate >RAM execution, or establish novelty.
