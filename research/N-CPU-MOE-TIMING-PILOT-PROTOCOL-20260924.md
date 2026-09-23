# n-cpu-moe minimal timing pilot protocol

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Capacity evidence commit: `5a8bbf08eb95069b1847f724e5d1be98c6392678`  
Capacity evidence: `research/results/n-cpu-moe-capacity-20260923T233416Z/`  
Status: IMPLEMENTED_MODEL_FREE / HOST_NOT_RUN

## Purpose

The published capacity-only gate admitted manual placements `N=12,16,20,24`
and rejected `N=0,4,8` on projected GPU headroom. It also froze a stock
auto-fit placement that is not equivalent to one simple `--n-cpu-moe N`
value.

The next experiment is deliberately smaller than the previously proposed full
frontier sweep.

The pilot measures exactly three fresh-process placements:

1. `auto-fit-frozen`;
2. `n-cpu-moe-12`;
3. `n-cpu-moe-24`.

`N=16` and `N=20` are NOT_RUN in this pilot.

## Discriminating questions

`auto-fit-frozen` versus `N=12` tests whether the stock fitter's
tensor/suffix-aware placement behaves materially differently from a coarse
N-based CPU-MoE boundary at the first capacity-admitted manual point.

`N=12` versus `N=24` tests the endpoint trade-off between the most
GPU-resident admitted manual placement and the all-experts-CPU manual
placement.

If those three points do not show a useful performance/resource trade-off,
measuring `N=16/N=20` is not justified.

## Authority and exactness

The target model and pinned llama.cpp runtime remain authoritative.

The pilot does not change routing, top-k, quantization, context, sampling,
token confirmation or expert semantics.

Each placement must generate exactly 64 token IDs with deterministic generation
policy. All three token-ID trajectories must have the same SHA-256.

This establishes greedy token trajectory equality only. It is not bitwise
tensor equality or numerical parity.

## Placement construction

At campaign start, `llama-fit-params` runs once with fit enabled and a
1024 MiB GPU target. Its emitted explicit `-c/-ngl/-ts/-ot` arguments are
parsed and frozen.

All timed `llama-server` runs use `--fit off`.

Manual placements use:

- `--ctx-size 4096`;
- `--gpu-layers all`;
- `--n-cpu-moe 12` or `24`;
- `--fit off`.

The frozen auto-fit placement replays only the explicit emitted arguments with
`--fit off`.

## Per-placement admission

Immediately before every placement, the runner measures:

- free GPU memory;
- MemAvailable;
- swap state;
- GPU temperature/pstate;
- competing GPU compute processes.

Any competing GPU compute process stops the campaign.

The exact placement is then re-estimated with
`llama-fit-params --fit-print on` under those fresh resources.

Admission requires:

- estimated device total + 1024 MiB GPU target + 16 MiB rounding guard <=
  measured free GPU memory;
- estimated host total + 2048 MiB host guard + 16 MiB rounding guard <=
  measured MemAvailable.

This is SOURCE_BACKED capacity admission. It is not measured peak VRAM/RAM and
is not proof that the subsequent run will fit.

## Runtime provenance and resource gates

After health PASS and before the measured request, the runner verifies the live
`llama-server` executable and mapped pre-hashed `libggml-cuda.so` against
the locked build provenance.

During each run, sampled telemetry records:

- whole-GPU used memory;
- GPU temperature;
- GPU power;
- process RSS;
- process swap;
- MemAvailable;
- SwapFree.

The campaign fails if:

- any GPU telemetry sample is invalid;
- the server process uses swap;
- measured free GPU memory falls below 1024 MiB;
- measured MemAvailable falls below 2048 MiB;
- required placement telemetry is absent;
- runtime provenance fails;
- server health fails;
- token count is not exactly 64;
- token trajectories differ.

## Timing scope

There is exactly one fresh-process observation per placement.

Recorded timing fields include client-observed TTFT, request wall time,
llama-server prompt tokens/s, decode tokens/s and server-ready time.

One observation per point is intentionally insufficient for a stable ranking.
The classification is:

`MEASURED_SINGLE_OBSERVATION_PILOT_DIAGNOSTIC`

The pilot can reject grossly poor placements or justify a repeated/full
campaign. It cannot establish a stable throughput/latency ranking.

## Stop condition

The output `next_gate` is always `MANUAL_REVIEW_REQUIRED`.

`N=16/N=20` and repeated observations remain unauthorized until the pilot is
reviewed.

## Operator entrypoint

The only authorized model-bearing entrypoint for this pilot is:

`scripts/run_n_cpu_moe_timing_pilot.sh MODEL.gguf OUTPUT_ROOT`

The output root is no-replace. Any failure is preserved and requires a new
campaign identity.

## Publication

A successful pilot ends with:

`PASS_STOCK_PLACEMENT_TIMING_PILOT`

Only then may it be prepared for Git publication with:

`scripts/publish_n_cpu_moe_timing_pilot_result.sh CAMPAIGN_ROOT PUBLISH_DIR`

The publication helper independently validates raw run artifacts against the
aggregate summary, requires exact trajectory PASS, runtime provenance PASS,
zero process swap and capacity admission for all three placements, then emits
a hash manifest and RESULT.md.

## Claim boundary

No Tesy speedup, physical PCIe/NVMe/DRAM byte, >RAM execution or novelty claim
follows from this pilot.
