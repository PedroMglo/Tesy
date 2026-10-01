# n-cpu-moe timing pilot interpretation

Date: 2026-09-24  
Result commit: `e4a63f8d6aeaa874936b63da8966710944bd0a17`  
Campaign: `n-cpu-moe-timing-pilot-20260924T003640Z`  
Classification: `MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC`

## Admitted evidence

All three fresh-process placements completed with:

- exact 64-token greedy trajectory equality;
- runtime executable / mapped CUDA backend provenance PASS;
- exact live argv identity PASS;
- revised placement telemetry PASS;
- zero process swap;
- complete GPU telemetry;
- current-host capacity admission PASS.

Host `CPU_Mapped` spans remain `NOT_COMPARABLE_MMAP_SPAN` and are not
treated as logical Host allocation or resident DRAM.

## Single-observation measurements

| Placement | TTFT ms | Prompt tok/s | Decode tok/s | Peak VRAM MiB | RSS GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| auto-fit-frozen | 583.35 | 265.42 | 48.902 | 6546 | 11.78 |
| n-cpu-moe-12 | 578.07 | 267.73 | 48.909 | 6548 | 11.78 |
| n-cpu-moe-24 | 910.13 | 169.75 | 35.422 | 1696 | 11.41 |

These are one observations each. They do not establish a stable ranking.

## Derived diagnostic comparisons

Relative to `auto-fit-frozen`, the single `N=12` observation changed:

- TTFT: -0.91%;
- prompt throughput: +0.87%;
- decode throughput: +0.014%;
- request wall time: -0.30%;
- peak VRAM: +2 MiB.

This pilot therefore detected no gross performance/resource separation between
the frozen stock auto-fit placement and coarse `N=12` on this workload.
This is **not** an equivalence claim.

Relative to `N=12`, the single `N=24` observation changed:

- TTFT: +57.44%;
- prompt throughput: -36.60%;
- decode throughput: -27.57%;
- request wall time: +44.08%;
- peak VRAM: -4852 MiB (-4.74 GiB).

This is a large diagnostic separation, so the admitted manual continuum now
contains a real performance-vs-VRAM trade-off worth resolving.

## Decision

Do not spend the next experiment repeating `auto-fit` versus `N=12`.

The cheapest discriminating next gate is a **manual continuum shape diagnostic**
covering:

- `N=12` anchor;
- `N=16`;
- `N=20`;
- `N=24` anchor.

Use one fresh-process observation per point under the same frozen workload and
the same exactness/provenance/resource gates.

The anchors are repeated in the new campaign so `N=16/N=20` are not compared
only across different campaign state.

This follow-up may locate a useful knee, but still must not be called a stable
Pareto frontier. Repeated/confirmatory timing is justified only after the curve
shape is known.

After this shape gate, choose the smallest relevant placement set for the
CPU-vs-transfer-vs-GPU expert crossover experiment.

## Claim boundary

No stable winner, Pareto frontier, Tesy speedup, physical PCIe/NVMe/DRAM
traffic, >RAM execution or novelty claim follows.
