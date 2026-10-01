# n-cpu-moe continuum-shape manual interpretation

Date: 2026-09-24  
Campaign: `n-cpu-moe-continuum-shape-20260924T083136Z`  
Publication commit: `97e26340ca8629fccb398580dc998f0ca2efe591`  
Classification: `DIAGNOSTIC_INTERPRETATION`

## Admitted measurements

The within-campaign single observations were:

| N | Decode tok/s | Peak VRAM MiB |
|---:|---:|---:|
| 12 | 43.444 | 6548 |
| 16 | 38.881 | 4932 |
| 20 | 34.551 | 3312 |
| 24 | 31.491 | 1696 |

All four observations passed the frozen exactness, provenance, placement and
resource gates. They remain one observation per point and do not establish a
stable ranking or Pareto frontier.

## Curve shape

Each additional four CPU-MoE layers released about 1.58 GiB of sampled peak
VRAM:

- N12 -> N16: 1616 MiB, decode cost 4.564 tok/s;
- N16 -> N20: 1620 MiB, decode cost 4.329 tok/s;
- N20 -> N24: 1616 MiB, decode cost 3.060 tok/s.

A simple descriptive linear fit of decode throughput versus sampled peak VRAM
has R^2 about 0.992 for these four observations. This is not a statistical
model; it only makes the absence of an obvious sharp knee explicit.

## Cross-campaign drift

The earlier three-point pilot measured:

- N12 decode: 48.909 tok/s;
- N24 decode: 35.422 tok/s.

The continuum campaign measured:

- N12 decode: 43.444 tok/s (-11.17%);
- N24 decode: 31.491 tok/s (-11.10%).

The N24/N12 decode ratio was:

- earlier pilot: 0.72425;
- continuum campaign: 0.72486.

The ratio changed by only about +0.083%, despite roughly 11% absolute
throughput drift at both anchors.

This is consistent with substantial common-mode campaign drift while the
relative anchor separation remained similar. With only two campaigns and one
observation per anchor, this is not evidence of stable performance or a
confidence interval.

## Decision

A balanced repeat campaign is **deferred**, not declared unnecessary.

It would be required before promoting a stable throughput ranking or Pareto
frontier, but it is not the cheapest experiment for the current architecture
question.

The placement-shape gate has already established a gradual performance/VRAM
trade-off with no obvious sharp knee. The next discriminating experiment is
therefore the mechanism-level:

`CPU-vs-transfer-vs-GPU expert crossover`.

That experiment must use real expert shapes and keep three quantities separate:

1. CPU-resident expert compute latency;
2. requested Host->GPU expert transfer latency/bytes;
3. already-resident GPU expert compute latency.

It must not call requested copy bytes physical PCIe traffic. If physical PCIe
traffic is claimed later, it requires an appropriate hardware/driver
instrument.

Before the crossover, re-establish an admitted GGUF expert shape/type
inventory with prospectively frozen dependency provenance. The previous raw
inventory values are useful context but were not admitted because transitive
gguf-py dependencies were not frozen prospectively.

## Claim boundary

No stable winner, Pareto frontier, Tesy speedup, physical PCIe/NVMe/DRAM
traffic, >RAM execution or novelty claim follows from this interpretation.
