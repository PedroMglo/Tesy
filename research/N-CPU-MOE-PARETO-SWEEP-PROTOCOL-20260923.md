# n-cpu-moe Pareto sweep protocol

Date: 2026-09-23
Base: `research/b0-b1-results-20260923@19044cc747c84b2eb5135b89f9ff10e1c1f83754`
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

All 14 observations must produce the same 64 generated token IDs for the
performance curve to qualify as an identical-trajectory comparison. A mismatch
is retained as `FAIL_TRAJECTORY_COMPARABILITY`; timing observations remain
diagnostic evidence but are not promoted as the same-work trajectory curve.

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
