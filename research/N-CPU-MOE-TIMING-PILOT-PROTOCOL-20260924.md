# n-cpu-moe minimal timing pilot protocol

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Capacity evidence commit: `5a8bbf08eb95069b1847f724e5d1be98c6392678`  
Capacity evidence: `research/results/n-cpu-moe-capacity-20260923T233416Z/`  
Classification: prospective diagnostic pilot

## Purpose

The published capacity gate admitted manual placements `N=12,16,20,24`
and rejected `N=0,4,8` on projected GPU headroom.

The stock auto-fit placement is not equivalent to one simple
`--n-cpu-moe N`: the published fitter output keeps `-ngl 25` and emits
explicit tensor overrides.

Before spending a balanced multi-point timing campaign, measure exactly three
fresh-process placements:

1. `auto-fit-frozen`;
2. `n-cpu-moe-12`;
3. `n-cpu-moe-24`.

`N=16` and `N=20` are NOT_RUN in this pilot.

## Discriminating questions

`auto-fit-frozen` versus `N=12` tests whether the stock fitter's
tensor/suffix-aware placement behaves materially differently from a coarse
prefix-based CPU-MoE boundary at the first capacity-admitted manual point.

`N=12` versus `N=24` brackets the admitted manual continuum and tests the
broad trade between more GPU-resident expert compute and the all-experts-CPU
endpoint.

If these three points do not expose a useful diagnostic trade, measuring
`N=16/N=20` is not automatically justified.

## Placement authority

The exact stock auto-fit placement is frozen by the published capacity evidence
commit. The pilot does **not** ask the fitter to choose a new auto placement.

The pilot loads:

- `research/results/n-cpu-moe-capacity-20260923T233416Z/auto-fit.json`;
- verifies that commit `5a8bbf08...` is an ancestor of the pilot HEAD;
- replays its exact `-c/-ngl/-ts/-ot` argv with `--fit off`.

Manual placements use:

- `--ctx-size 4096`;
- `--gpu-layers all`;
- `--n-cpu-moe 12` or `24`;
- `--fit off`.

The target remains authoritative. No routing, top-k, quantization, context,
sampling, token confirmation or expert semantics are changed.

## Frozen workload

- locked gpt-oss-20b MXFP4 GGUF;
- pinned llama.cpp commit;
- committed B0/B1 diagnostic prompt;
- context: 4096;
- parallel: 1;
- CPU threads / batch threads: 12 / 12;
- exactly 64 generated tokens;
- temperature: 0;
- top-k: 1;
- seed: 42;
- prompt cache disabled;
- server warmup disabled;
- fresh `llama-server` process per placement.

There is exactly one observation per placement. This is not confirmatory
performance evidence.

## Provenance gates

Before model timing:

- locked model verification PASS;
- reference-host identity PASS;
- no competing GPU compute process;
- clean Tesy and llama.cpp worktrees;
- pinned source/feature probe through `llama-cli`;
- locked CMake/compiler/CUDA/server/`libggml-cuda.so` provenance PASS;
- published capacity evidence identity PASS;
- prompt/backend/model hashes recorded.

After each server health PASS and before its request:

- verify `/proc/<pid>/exe`;
- verify the pre-hashed `libggml-cuda.so` is the backend actually mapped by
  that process.

## Capacity admission

Two admission layers are required.

First, at campaign start, pinned `llama-fit-params --fit-print on` estimates
all three exact placements under the measured campaign-start GPU/RAM state.

Second, immediately before every individual load, the runner:

- measures free GPU memory;
- measures MemAvailable/SwapFree;
- records GPU temperature/pstate;
- rejects competing GPU compute processes;
- re-evaluates the same placement estimate against those fresh resources.

Admission requires:

- estimated device total + 1024 MiB GPU target + 16 MiB rounding guard <=
  current free GPU memory;
- estimated host total + 2048 MiB host guard + 16 MiB rounding guard <=
  current MemAvailable.

This is `SOURCE_BACKED_MEMORY_ESTIMATE`, not measured peak VRAM/RAM and not
proof that the subsequent load will fit.

## Exactness gate

The first successful run establishes the deterministic trajectory.

Every later placement must have:

- exactly 64 generated token IDs;
- `timings.predicted_n == 64`;
- the exact same token-ID SHA-256.

Mismatch stops and preserves the campaign.

This is greedy token equality only, not bitwise tensor equality, numerical
parity or sampling-distribution equivalence.

## Runtime resource gates

Sampled telemetry records:

- whole-GPU used memory;
- GPU temperature;
- GPU power;
- process RSS;
- process swap;
- MemAvailable;
- SwapFree.

Every run must have:

- valid GPU telemetry sufficient to establish peak use;
- process VmSwap == 0;
- observed free GPU memory at peak >= 1024 MiB;
- observed MemAvailable >= 2048 MiB;
- non-empty placement/load evidence;
- runtime backend provenance PASS.

OOM, missing telemetry, resource violation, token mismatch or provenance
failure stops the campaign and requires a new identity.

## Timing scope

Recorded fields include:

- server-ready wall time;
- client-observed TTFT;
- request wall time;
- prompt tokens/s;
- decode tokens/s;
- observed peak GPU memory;
- RSS/swap;
- thermal/power samples.

The aggregate classification is
`MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC`.

One sample per placement is intentionally insufficient for a stable ranking or
Pareto claim. The pilot can only decide whether a larger experiment is worth
buying.

The summary must set:

`next_gate = MANUAL_REVIEW_REQUIRED`.

## Operator entrypoint

The only authorized model-bearing entrypoint is:

```bash
campaign="results/n-cpu-moe-timing-pilot-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_n_cpu_moe_capacity_pareto.sh \
  --timing-pilot \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

The output root is no-replace. Never reuse a failed campaign identity.

A successful pilot ends with:

`PASS_DIAGNOSTIC_STOCK_PLACEMENT_TIMING_PILOT`.

## Publication boundary

Only a successful pilot may be published.

Use:

```bash
python -m tesy.publish_timing_pilot "$campaign" "$publish_dir"
```

The publisher stages only derived summaries, provenance and identities.

Raw request streams, server logs, resource samples, pre-run snapshots and
placement files remain outside Git. Their byte sizes and SHA-256 identities are
recorded in the publication manifest.

## Decision after pilot

Do not fill in `N=16` or `N=20` automatically.

Review:

- exact trajectory equality;
- campaign-start and per-run capacity admission;
- realized placement evidence;
- TTFT/prompt/decode timing;
- observed VRAM/RSS/swap;
- pre-run headroom and thermal/resource state.

Then choose whether to kill the manual continuum, repeat a suspicious point,
freeze a small confirmatory set, or proceed to the
CPU-vs-transfer-vs-GPU crossover gate.

## Claim boundary

No Tesy speedup, physical PCIe/NVMe/DRAM byte, >RAM execution or novelty claim
follows from this pilot.
