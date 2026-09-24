# n-cpu-moe Pareto sweep protocol

Date: 2026-09-23
Base: `main@2de6209032ef2d9a2b5c806be8a6ef183e483eeb` (restacked replacement for historical PR #8)
Branch: `research/n-cpu-moe-pareto-sweep-20260923`
Classification: prospective diagnostic

## Question

For the exact locked gpt-oss-20b and stock llama.cpp pin, how does progressively
keeping expert layers on CPU trade decode/prompt latency against observed VRAM?

This is cheaper and more representative than writing an isolated custom expert
kernel before the stock placement continuum is known.

## Frozen sweep

The real GGUF inventory has 24 MoE layers. Sweep:

```text
N = 0, 4, 8, 12, 16, 20, 24
```

where `N` is passed to stock `--n-cpu-moe N`.

Order is balanced:

```text
0,4,8,12,16,20,24,24,20,16,12,8,4,0
```

Thus every point has two fresh-process observations and thermal/order drift is
partially balanced.

## Frozen workload

Same model, backend pin and committed prompt as B0/B1:
- context 4096;
- parallel 1;
- 12 CPU threads and batch threads;
- automatic GPU layer fit, 1024 MiB fit target;
- 64 generated tokens;
- temperature 0;
- top-k 1;
- seed 42;
- prompt cache disabled;
- warmup disabled;
- fresh llama-server process for every observation.

No winner threshold is defined. This is a calibration/diagnostic sweep.

## Required telemetry

Per observation:
- server ready time;
- client TTFT;
- server prompt/decode timing;
- peak process RSS/swap;
- peak observed GPU memory;
- minimum MemAvailable/SwapFree;
- maximum GPU temperature and available power samples;
- raw server log identity/hash.

Aggregate by N:
- mean/min/max TTFT;
- mean prompt tok/s;
- mean decode tok/s;
- mean/peak VRAM;
- mean RSS;
- all process swap values;
- generated-token trajectory SHA-256 per observation;
- decode-throughput vs VRAM Pareto set.

## Endpoint sanity

N=0 should be compared descriptively with prior B0.
N=24 should be compared descriptively with prior `--cpu-moe` B1.

A difference is evidence to investigate, not permission to adjust the sweep.

Each observation must produce exactly 64 generated token IDs. The first valid
trajectory becomes the reference and every subsequent observation is compared
immediately. The runner stops on the first mismatch and retains that campaign
as `FAIL_TRAJECTORY_COMPARABILITY`; it does not spend the remaining expensive
measurements after the stop condition becomes true.

## Stop conditions

Preserve and stop the affected campaign on:
- nonzero server/request failure;
- missing final server timings;
- no TTFT;
- OOM;
- process VmSwap > 0;
- missing GPU telemetry for an observation;
- generated-token trajectory mismatch across placements;
- model/backend/worktree identity mismatch.

## Claim boundary

This measures stock placement behavior only.

It does not measure physical PCIe/NVMe expert traffic, does not prove a Tesy
cache benefit, does not test >RAM behavior and does not establish novelty.

The next gate after this sweep is chosen from the observed Pareto frontier.


## Failed campaign amendment — 2026-09-23T214340Z

Campaign output root:
`results/n-cpu-moe-sweep-20260923T214340Z`.

Status:
`FAIL_CLIENT_STREAM_CLASSIFICATION`.

The first observation reached a valid server completion with
`predicted_n = 64`, but Tesy's client counted 67 token IDs and stopped
fail-closed.

Pinned llama-server source inspection established the cause before retry:
prompt-progress events are emitted through
`send_partial_response(slot, {}, true)`. In the non-OAI serializer these
events contain `prompt_progress` and also serialize the default
`completion_token_output.tok` in the `tokens` array. These are progress
placeholders, not generated-token trajectory entries.

Correction:
Tesy ignores `tokens` only when the same SSE event contains
`prompt_progress`. Normal generated partial events remain subject to strict
integer-token accounting and the final count must still equal
`timings.predicted_n`.

The failed output root remains preserved and is not reused. Retry requires a
new campaign identity. No model, backend, placement sweep, sampling, token-count
or performance criterion changed.


## Review hardening

Before model measurement the runner now executes Tesy's pinned backend probe
against the selected `llama-server` and source checkout. A clean but wrong
llama.cpp revision therefore fails before the sweep.

The 64-token requirement is enforced per observation, not inferred from
`predicted_n` after the sweep, and cross-placement trajectory equality is
checked inside the loop after every completed request.


## Restack/review admission hardening

Before any model measurement the restacked runner additionally requires:

- the frozen B0/B1 NVIDIA driver, CUDA compiler, GCC/G++ and CMake identity
  from `configs/b0-b1-toolchain.lock.json`;
- the `llama-cli` feature/source probe against the exact pinned clean source;
- embedded `llama-cli --version` and `llama-server --version` commit IDs
  matching that source pin;
- `--verbosity 4` loader telemetry;
- for every requested `N>0`, all six merged gpt-oss expert tensors
  (gate/up/down weight+bias) in each of layers `0..N-1` must emit an
  explicit loader override to a CPU-class buffer;
- CUDA0 model-buffer telemetry and, for `N>0`, a CPU model-buffer record;
- per-run SHA-256 for raw server stdout, raw server stderr and the parsed
  placement artifact;
- the final summary rechecks `placement_status=PASS` and records the raw-log
  hashes.

The placement gate intentionally accepts the CPU-class buffer actually selected
by the pinned loader (for example `CPU` or an eligible CPU extra/repack
buffer). It does not infer placement from requested flags alone.

These gates do not retroactively admit the earlier B0/B1 source campaign.
