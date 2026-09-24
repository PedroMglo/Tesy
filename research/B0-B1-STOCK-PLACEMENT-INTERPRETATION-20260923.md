# B0/B1 stock placement interpretation

Date: 2026-09-23  
Source campaign: `research/results/b0-b1-20260923T212353Z/`  
Classification: `SUPERSEDED_INCONCLUSIVE_INTERPRETATION`

## Admission correction

The retained source campaign is `INCONCLUSIVE_RERUN_REQUIRED` for a
same-work placement comparison.

Review established three independent admission failures:

1. the required placement artifacts were empty, so realized B0/B1 placement
   was not demonstrated;
2. the campaign did not retain the full frozen backend/toolchain provenance
   required for a hardware-bearing comparison;
3. generated token IDs were not retained, so equal trajectories across arms
   were not established.

Therefore the measurements below remain descriptive observations of the
executed runs only. They must not be promoted to a placement winner, speedup,
or admitted B0-vs-B1 trade-off.

## Retained descriptive observations

The invalidated campaign recorded these descriptive means:

- B0 automatic placement: TTFT 539.82 ms, prompt 286.66 tok/s, decode
  51.11 tok/s, observed peak GPU memory 6.70 GiB, process swap 0;
- B1 `--cpu-moe`: TTFT 884.48 ms, prompt 174.69 tok/s, decode
  34.74 tok/s, observed peak GPU memory 1.68 GiB, process swap 0.

Those numbers are measurements of the processes that ran. Because placement,
toolchain provenance and token-trajectory comparability were not admitted,
statements such as "B0 is materially faster than B1" are not admitted
conclusions from this campaign.

## Historical next-step boundary

These descriptive endpoints motivated a prospective `--n-cpu-moe N`
continuum protocol. That protocol is a new experiment with its own admission
gates; it does not repair or retroactively validate the B0/B1 source campaign.

Later stacked work may supersede or retire the direct sweep if source/static
feasibility invalidates its composition.

No Tesy-native cache, prefetcher or custom expert kernel is authorized by this
inconclusive B0/B1 result.
