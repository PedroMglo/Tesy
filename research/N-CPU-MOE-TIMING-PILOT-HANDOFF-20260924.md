# n-cpu-moe timing pilot handoff

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Base evidence commit: `5a8bbf08eb95069b1847f724e5d1be98c6392678`  
Capacity campaign: `research/results/n-cpu-moe-capacity-20260923T233416Z/`

## State

The published capacity gate admitted manual `N=12,16,20,24` and rejected
`N=0,4,8` for projected GPU headroom.

The stock auto-fit placement is not equivalent to a single manual `N`; its
frozen explicit argv uses `-ngl 25` plus tensor overrides that move block-12
FFN tensors and a suffix of later expert tensors to CPU.

A full multi-point timing sweep is not authorized yet.

## Next gate

Run only the three-point diagnostic pilot:

1. `auto-fit-frozen`;
2. `n-cpu-moe-12`;
3. `n-cpu-moe-24`.

The runner mode is:

```text
scripts/run_n_cpu_moe_capacity_pareto.sh --timing-pilot
```

It rechecks current-host capacity for all three placements before starting any
server, then performs one fresh-process observation per placement.

## Required local validation

Before model-bearing execution:

```bash
ruff check .
pytest -q
bash -n scripts/*.sh
python -m compileall -q src tests
```

No full GitHub Actions run is required for this development gate. The repository
workflow is configured so the full matrix runs only at `Ready for review` or
manual dispatch.

## Pilot stop rules

Preserve and stop on:

- source/build/model/host provenance mismatch;
- current-host capacity rejection for any of the three placements;
- model/server load failure or OOM;
- runtime backend mapping mismatch;
- realized CUDA0/Host model buffers differing from the same-placement
  fit-print projection by more than 2 MiB;
- missing placement evidence;
- process swap;
- measured GPU/host headroom violation;
- missing valid GPU telemetry;
- generated-token trajectory mismatch.

Never reuse a failed output root.

## Publication

Only a completed pilot with
`PASS_DIAGNOSTIC_STOCK_PLACEMENT_TIMING_PILOT` may be published.

Use:

```bash
python -m tesy.publish_timing_pilot "$campaign" "$publish_dir"
```

The publisher copies only derived summaries/provenance/identity artifacts.
Raw request streams, server logs, resource samples and placement files remain
local; the publication manifest records their byte sizes and SHA-256 identities.

The result publication must use a new dedicated branch based on the exact pilot
implementation branch.

## Decision after pilot

Do not fill in `N=16` or `N=20` automatically.

First inspect:

- exact trajectory equality;
- live capacity recheck;
- realized placement evidence;
- TTFT/prompt/decode timing;
- observed VRAM/RSS/swap;
- thermal/resource state.

Only then choose whether to:

- kill the manual continuum;
- repeat a suspicious point;
- freeze a small confirmatory set;
- proceed to the CPU-vs-transfer-vs-GPU crossover gate.

No Tesy-native cache, prefetch, speculation, >RAM execution or gpt-oss-120b
run is authorized by this pilot alone.
