# Mixed-residency async steady-tail preparation handoff

Date: 2026-09-24

Branch:
`research/mixed-residency-async-tail-order-20260924`

Base commit:
`11f4759cb7012c4dca09b815d11bee36a6d0253f`

Base tree:
`cee8a595c44b3b5be3ad249756faa2ab7bfbb75c`

Evidence class:
`POST_HOC_DIAGNOSTIC + PROSPECTIVE_TAIL_GATE_IMPLEMENTED_NOT_RUN`

## Objective

Before implementing routed-layer integration, determine whether the h=2/h=3
>2 ms aggregate async p95 observed in the successful isolated campaign is a
steady async tail problem or a comparator-order transition effect.

No native scheduling change is introduced in this phase.

## Input evidence

The published physical async campaign:

`mixed-residency-async-overlap-20260924T152625Z`

established:

- `ASYNC_OVERLAP_MEASURED_GO`;
- weighted serial median 0.4950063228 ms;
- weighted async median 0.4298951194 ms;
- 13.1536% reduction against a preregistered 10% gate;
- numerical parity PASS;
- physical-host/provenance/resource gates PASS.

Its aggregate async p95 was:

- h=2: 2.1747312 ms;
- h=3: 2.1158442 ms.

## Cheap post-hoc discrimination

The paired benchmark alternates even samples as serial→async and odd samples
as async→serial. Warmups end in async.

Reconditioning the existing raw samples shows:

- h=2 async-after-async p95: 0.7152868 ms;
- h=2 serial-after-serial p95: 0.8191348 ms;
- h=2 serial→async p95: 2.3968682 ms;
- h=3 async-after-async p95: 0.7026312 ms;
- h=3 serial-after-serial p95: 0.6341700 ms;
- h=3 serial→async p95: 2.1621876 ms.

The serial→async transition p95 is ~3.35x the steady async p95 for h=2 and
~3.08x for h=3.

This source campaign provides only 10 steady observations per path, so its
nearest-rank p95 is effectively a maximum. The reconditioned values are
diagnostic, not a new acceptance result.

Detailed derivation:
`research/MIXED-RESIDENCY-ASYNC-ORDER-EFFECT-DIAGNOSIS-20260924.md`.

## Alternatives considered

1. Ignore the aggregate p95 because the median gate passed.
   Rejected: would hide a real tail observation.

2. Proceed directly to routed-layer integration and let that experiment decide.
   Rejected for now: higher implementation complexity before a cheaper
   discriminating experiment.

3. Repeat the same native async mechanism with enough paired samples to
   separate steady and transition buckets.
   Selected.

## Prospective implementation

No native C++ path is changed.

The existing async runner now accepts, with unchanged defaults:

- `TESY_ASYNC_SAMPLES` (default 21);
- `TESY_ASYNC_TAIL_ORDER` (default 0).

Tail-order mode requires exactly 81 samples and runs
`tesy.mixed_residency_async_tail_order`.

Dedicated entrypoint:

`scripts/run_mixed_residency_async_tail_order.sh`.

It fixes:

- 81 paired samples;
- the same 3 warmups;
- 5 inner repetitions;
- the same native scheduling identity;
- the same model/backend/histogram/provenance/resource gates.

## Frozen decision

Gate only h=2 and h=3.

For both require:

`AA_median <= 0.90 * SS_median`

and:

`AA_p95 <= 1.10 * SS_p95`.

Decision:

- both cases pass both thresholds:
  `ASYNC_STEADY_TAIL_GO`;
- otherwise:
  `ASYNC_STEADY_TAIL_NO_GO`.

h=1 is retained as a control only.

The p95 budget is frozen prospectively before the new campaign. The existing
small-n h=3 diagnostic is 10.8% worse than steady serial, so the 10% threshold
does not retroactively guarantee PASS.

## Source/static validation completed

**REPRODUZIDO / PASS**:

- new Python/test/contract files have no >100-character lines;
- order slices are explicit and match the existing `measure_paired` schedule;
- tail mode requires exactly 81 samples;
- runner defaults remain the previously measured 21-sample behavior;
- wrapper sets only sample count and tail-analysis mode;
- native source/scheduling is unchanged by this branch;
- no `std::thread`, routing change, prefetch or cache policy is introduced.

## Tests not run in this environment

Final branch model-free tests:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Shell syntax:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Native CUDA build:
`NOT_RUN_REFERENCE_HOST`.

Physical tail-order campaign:
`NOT_RUN_REFERENCE_HOST`.

## Stop conditions

Reuse all existing async campaign correctness, provenance and resource stop
conditions.

Additionally stop before promotion if:

- raw sample count is not exactly 81;
- paired scheduling identity differs;
- conditioned bucket cardinalities are not 41/40/40/40;
- conditioned timings are non-finite/non-positive;
- analyzer output is malformed.

A valid `ASYNC_STEADY_TAIL_NO_GO` is a completed negative diagnostic, not an
execution failure.

## Next gate

If the physical result is `ASYNC_STEADY_TAIL_GO`, then and only then prepare
the smallest routed-layer/backend integration with exact routing and a
same-layer serial comparator.

If it is `ASYNC_STEADY_TAIL_NO_GO`, do not integrate the current async
mechanism and do not advance to prefetch.

No physical campaign was executed while preparing this branch.
