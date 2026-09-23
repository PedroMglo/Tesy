# stock placement capacity/Pareto protocol

Date: 2026-09-23  
Base evidence branch: `research/n-cpu-moe-fail-20260923T220215Z`  
Implementation branch: `research/n-cpu-moe-fit-conflict-20260923`  
Classification: prospective diagnostic

## Question

For the locked gpt-oss-20b GGUF and pinned stock llama.cpp, what stock
CPU/GPU expert placements are both capacity-admissible on the reference host
and non-dominated on decode throughput versus observed peak GPU memory?

This protocol replaces the retired direct
`--fit on --n-cpu-moe N` sweep. It does not assume that the stock auto-fit
placement is representable by a single `N`.

## Frozen model and workload

Use the existing locked:
- gpt-oss-20b MXFP4 GGUF identity and checksum;
- llama.cpp pin;
- committed B0/B1 diagnostic prompt.

Timed runs freeze:
- context: 4096;
- parallel: 1;
- CPU threads / batch threads: 12 / 12;
- 64 generated tokens;
- temperature 0;
- top-k 1;
- seed 42;
- prompt cache disabled;
- warmup disabled;
- fresh `llama-server` process per observation.

No performance threshold or winner is preregistered. The output is a
calibration frontier.

## Recommended operator sequence

Run the cheap estimator gate first under a dedicated output root:

```bash
bash scripts/run_n_cpu_moe_capacity_pareto.sh --capacity-only \
  MODEL.gguf CAPACITY_OUTPUT_ROOT
```

This mode performs Stages A-C, writes the frozen auto-fit placement and all
manual capacity estimates, then exits before starting `llama-server` timing
observations.

Review `capacity-summary.json` before authorizing Stage D. A later full
capacity+timing campaign must use a new output root and repeats the admission
gate so its measured campaign-start resources remain self-contained.

## Stage A — provenance and measured campaign-start resources

Before capacity estimation or timing:

- verify model identity;
- verify reference-host identity;
- require exactly one expected GPU;
- reject competing GPU compute processes;
- capture GPU free/total memory, RAM available and swap state;
- verify Tesy and llama.cpp worktrees are clean;
- use pinned `llama-cli` for the backend feature/source-surface probe defined
  by `configs/backends.lock.json`;
- validate the actual execution `llama-server` surface separately for its
  server-required flags;
- validate the actual estimator `llama-fit-params` surface separately for its
  fit-required flags;
- validate `configs/reference-llama-toolchain.json` against the active
  llama.cpp `CMakeCache.txt`;
- require the measured Release/CUDA-89 GCC 15.3.1 / nvcc 13.3.73 toolchain;
- require `llama-server` and `llama-fit-params` to come from that same build;
- require the previously measured stock `llama-server` and
  `libggml-cuda.so` SHA-256 identities;
- require `CUDA0` visibility from both binaries and successful dynamic
  dependency resolution;
- record `build-provenance.json`, Tesy HEAD, llama.cpp HEAD and hashes of the
  prompt and relevant binaries.

The campaign output root is new/no-replace.

## Stage B — freeze the stock auto-fit baseline

Run the pinned `llama-fit-params` outside the timed campaign path with:

```text
--ctx-size 4096 --fit on --fit-target 1024
```

The utility must emit exactly one fitted CLI containing:
- `-c`;
- `-ngl`;
- optional `-ts`;
- optional `-ot`.

Tesy parses that output fail-closed and rejects unknown/duplicate fields. The
emitted context must remain exactly 4096.

The resulting argv is the authoritative stock auto-fit placement for this
campaign start. Timed baseline observations replay those explicit arguments
with `--fit off`.

This prevents fitting work or a different fit decision from occurring inside
the timed baseline observations.

## Stage C — capacity admission for manual n-cpu-moe points

Candidate manual points remain:

```text
N = 0, 4, 8, 12, 16, 20, 24
```

For each candidate, run pinned `llama-fit-params --fit-print on` with:

```text
--ctx-size 4096 --gpu-layers all --n-cpu-moe N --fit off
```

The estimator reports integer-MiB model/context/compute requirements for the
accelerator and host. This path is used only for admission.

A manual point is admitted only if both conditions hold against the measured
campaign-start resources:

```text
GPU estimate total + 1024 MiB target + 16 MiB rounding guard
    <= measured campaign-start GPU free memory

Host estimate total + 2048 MiB guard + 16 MiB rounding guard
    <= measured campaign-start MemAvailable
```

The 16 MiB term is a conservative guard around integer-MiB reporting; it is not
a hardware measurement.

Rejected points are not deliberately loaded to "prove" OOM.

If fewer than two manual points are admitted, stop before timing with
`NO_GO_N_CPU_MOE_CAPACITY_FRONTIER`.

## Stage D — timed placement observations

Timed placements are:
- `auto-fit-frozen`: the explicit stock auto-fit argv from Stage B;
- each admitted manual `n-cpu-moe=N` point from Stage C.

Every timed run uses `--fit off`.

Order:

```text
auto,
admitted N ascending,
admitted N descending,
auto
```

Thus every admitted manual point and the auto-fit baseline have two
fresh-process observations.

## Exactness gate

Every observation must:
- produce exactly 64 generated token IDs;
- report `timings.predicted_n == 64`;
- have the same generated-token trajectory SHA-256 as the first successful
  observation.

A mismatch stops and preserves the campaign as a correctness failure. Timing
from mismatched trajectories is not comparable.

This is greedy token equality only. It is not bitwise tensor equality or a
sampling-distribution claim.

## Runtime resource gates

Every timed observation must retain valid GPU telemetry and satisfy:
- process VmSwap == 0;
- observed GPU free memory at measured peak >= 1024 MiB;
- observed MemAvailable >= 2048 MiB.

Any violation stops the campaign. Estimator admission never overrides measured
runtime resource evidence.

## Required telemetry

Per timed observation:
- explicit server command;
- placement identifier and manual `N` when applicable;
- server-ready wall time;
- client TTFT;
- server prompt/decode timing;
- exact token IDs and trajectory hash;
- peak observed GPU memory and derived minimum observed free GPU memory;
- process RSS/swap;
- minimum system MemAvailable/SwapFree;
- GPU temperature and available power samples;
- non-empty placement/load log excerpt;
- `runtime-provenance.json` proving the live process executable and mapped
  `libggml-cuda.so` match the pre-hashed build identity.

Capacity estimator stdout/stderr and parsed JSON are also retained for every
candidate, including rejected points.

## Aggregate

For every timed placement report:
- two raw observations;
- mean TTFT;
- mean prompt tok/s;
- mean decode tok/s;
- mean/maximum observed peak GPU memory;
- mean RSS;
- maximum process swap;
- maximum GPU temperature;
- telemetry failures.

Compute the non-dominated set on:
- higher mean decode throughput;
- lower mean observed peak GPU memory.

Do not rank placements by a single synthetic score.

## Stop conditions

Preserve and stop the campaign on:
- provenance, locked build/toolchain/backend identity or host-identity mismatch;
- dirty Tesy or llama.cpp worktree;
- invalid fitted CLI;
- unexpected context change;
- server/request nonzero failure;
- OOM;
- missing final timings or TTFT;
- token trajectory mismatch;
- process swap;
- missing GPU telemetry;
- runtime GPU or host headroom violation;
- corrupted/missing required artifacts;
- live runtime backend mapping mismatch or deleted mapped backend library.

Debugging requires a new campaign identity.

## Claim boundary

Stage C is `SOURCE_BACKED_CAPACITY_GATE`, not a memory measurement.

Stage D produces measured timing/resource observations on one locked
model/workload/host. The Pareto set is descriptive for those observations.

Nothing here measures physical PCIe or NVMe expert traffic, validates >RAM
execution, demonstrates a Tesy speedup/cache/prefetch benefit, or establishes
scientific novelty.
