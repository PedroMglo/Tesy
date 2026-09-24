# B0/B1 stock placement interpretation

Date: 2026-09-23  
Source campaign: `research/results/b0-b1-20260923T212353Z/`  
Classification: `SUPERSEDED_INCONCLUSIVE_INTERPRETATION`

## Admission correction

The source campaign's retained `RESULT.md` classifies the B0/B1 comparison as
`INCONCLUSIVE_STOCK_B0_B1_DIAGNOSTIC` and requires a rerun.

Three independent admission failures were established in review:

1. all four required `placement.txt` artifacts are empty, so realized
   placement was not verified;
2. the campaign did not retain the full backend/toolchain identity required by
   the prospective protocol;
3. generated token IDs were not retained, so equal trajectories across B0/B1
   were not established.

Therefore the earlier interpretation below must not be used to establish a
performance winner or to authorize a mechanism based on a same-work comparison.

## Retained descriptive observations

The invalidated campaign recorded the following descriptive means:

- B0 automatic placement: TTFT 539.82 ms, prompt 286.66 tok/s, decode
  51.11 tok/s, observed peak GPU memory 6.70 GiB, process swap 0;
- B1 `--cpu-moe`: TTFT 884.48 ms, prompt 174.69 tok/s, decode
  34.74 tok/s, observed peak GPU memory 1.68 GiB, process swap 0.

Those numbers remain measurements of the executed runs, but they are not an
admitted identical-trajectory placement comparison.

In particular, statements such as "B0 is materially faster than B1" are not
admitted conclusions from this campaign.

## Replacement decision

The next experiment is not the retired direct
`--fit on --n-cpu-moe N` sweep.

Use the prospective capacity-gated stock placement frontier in
`research/N-CPU-MOE-CAPACITY-PARETO-PROTOCOL-20260923.md`.

That campaign re-establishes a frozen stock auto-fit baseline with explicit
placement arguments, enforces exact 64-token trajectory equality, and admits
manual `--n-cpu-moe N` points through the pinned source estimator before
timing.

No Tesy-native cache, prefetcher or custom expert kernel is authorized by the
invalidated B0/B1 result.
