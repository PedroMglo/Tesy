# Mixed-residency async order-effect diagnosis

Date: 2026-09-24

Source campaign:
`research/results/mixed-residency-async-overlap-20260924T152625Z/`

Source measurement commit:
`3500fd4dadeac6303091577ea3a275328810feac`

Evidence class:
`POST_HOC_ORDER_CONDITIONED_DIAGNOSTIC`

## Observation

The published async campaign passed its preregistered weighted-median gate:

- weighted serial median: 0.4950063228 ms;
- weighted async median: 0.4298951194 ms;
- reduction: 13.1536%;
- decision: `ASYNC_OVERLAP_MEASURED_GO`.

However, aggregate async p95 was high for:

- h=2: 2.1747312 ms;
- h=3: 2.1158442 ms.

The paired measurement schedule alternates:

- even sample index: serial block, then async block;
- odd sample index: async block, then serial block.

Warmup pairs end in async.

Therefore, after sample 0:

- odd async samples are async-after-async observations;
- even async samples are serial-to-async transition observations;
- odd serial samples are async-to-serial observations;
- even serial samples from index 2 onward are serial-after-serial observations.

## Reconditioned source data

The existing 21-sample campaign yields only 10 steady observations per path.
Nearest-rank p95 with n=10 equals the maximum and is therefore too fragile for
a tail acceptance claim.

| h | SS median ms | SS p95 ms | AA median ms | AA p95 ms | SA p95 ms | AA median / SS | AA p95 / SS | SA p95 / AA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.641989 | 0.683713 | 0.580795 | 0.658604 | 0.653557 | 0.9047 | 0.9633 | 0.9923 |
| 2 | 0.541471 | 0.819135 | 0.455104 | 0.715287 | 2.396868 | 0.8405 | 0.8732 | 3.3509 |
| 3 | 0.568572 | 0.634170 | 0.440819 | 0.702631 | 2.162188 | 0.7753 | 1.1080 | 3.0773 |

Legend:

- SS = serial-after-serial;
- AA = async-after-async;
- SA = async-after-serial.

The large h=2/h=3 aggregate spikes are concentrated in the serial-to-async
transition bucket. h=2 steady async p95 is below steady serial p95. h=3 steady
async p95 is 10.8% above steady serial p95, but this is one maximum from only
10 steady samples.

## Interpretation

This is evidence that the published aggregate p95 mixes two different
questions:

1. steady candidate latency;
2. comparator-mode transition latency introduced by the paired benchmark.

The current data do **not** prove that the async mechanism has a >2 ms
steady-state p95. They also do not prove the opposite.

The production candidate would not alternate serial and async implementations
for the same h merely to compare them, so serial-to-async comparator
transition cost must not be silently relabelled as steady runtime tail.

A future routed-layer implementation can still transition between different
routing/residency cases, so this observation is not permission to ignore tail
latency. It motivates a cheaper isolated disambiguation before backend
integration.

## Decision

Do not advance directly to routed-layer integration yet.

Run one prospective order-conditioned campaign with more samples using the
same native async mechanism and same model/histogram identities. Gate the
steady h=2/h=3 candidate before buying routed-layer integration complexity.

No prefetch, cache-policy, speculation or full-model work is authorized by
this diagnosis.
