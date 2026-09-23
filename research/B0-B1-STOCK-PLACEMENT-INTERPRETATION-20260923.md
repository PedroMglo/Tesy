# B0/B1 stock placement interpretation

Date: 2026-09-23
Source campaign: `research/results/b0-b1-20260923T212353Z/`
Classification: DERIVED_FROM_MEASURED_STOCK_DIAGNOSTIC

## Observed endpoints

Two fresh-process repetitions were measured for each stock arm.

Mean B0 (automatic placement):
- TTFT: 539.82 ms;
- prompt: 286.66 tok/s;
- decode: 51.11 tok/s;
- peak observed GPU memory: 6.70 GiB;
- process swap: 0.

Mean B1 (`--cpu-moe`):
- TTFT: 884.48 ms;
- prompt: 174.69 tok/s;
- decode: 34.74 tok/s;
- peak observed GPU memory: 1.68 GiB;
- process swap: 0.

Relative to B0, B1:
- increased TTFT by ~63.85%;
- reduced prompt throughput by ~39.06%;
- reduced decode throughput by ~32.04%;
- reduced peak observed GPU memory by ~74.97%, freeing ~5.02 GiB.

These are descriptive results from this diagnostic workload, not universal
backend properties.

## Decision

Do not collapse the result to "B0 wins".

B0 is materially faster on this admitted model/workload. B1 buys a large VRAM
reduction at a material latency/throughput cost. For future models that cannot
fit the B0 placement envelope, that capacity trade is potentially more
important than raw B0 speed.

The next cheap experiment is therefore the stock continuum already exposed by
llama.cpp: `--n-cpu-moe N`.

No Tesy-native cache, prefetcher or custom kernel is justified before the
VRAM/performance Pareto curve is known.
