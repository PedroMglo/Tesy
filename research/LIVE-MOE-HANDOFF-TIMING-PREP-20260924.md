# Live MoE handoff timing preparation

Date: 2026-09-24

Branch:
`research/live-moe-handoff-timing-20260924`

Development base:
`research/live-moe-handoff-exactness-20260924`

Evidence class:
`SOURCE_AUDITED / IMPLEMENTED_NOT_RUN / PHYSICAL_NOT_RUN`.

## Admitted prerequisite

The physical correctness-only campaign established:

`LIVE_MOE_HANDOFF_EXACTNESS_GO`.

For the repeated layer-0 event:

- token `2167`;
- experts `[1, 13, 17, 21]`;
- final routing weights from `ffn_moe_weights_softmax-0`;
- stock-reference and handoff activations bitwise equal;
- h=2/h=3 serial-vs-stock PASS;
- h=2/h=3 async-vs-stock PASS;
- h=2/h=3 async-vs-serial PASS;
- maximum relative error vs stock `5.60445568e-08`;
- cosine 1.0;
- zero process swap.

Focused validation passed 61 tests and the full model-free suite passed 258
at the admitted measurement identity.

This authorizes timing of the exact same boundary only.

## Measurement question

The next useful question is not an arbitrary percentage speedup.

It is:

**how much measured latency budget remains for output reinjection while still
staying below the within-process stock MoE comparator?**

The campaign therefore publishes:

`budget = stock latency - candidate latency`

for median and p95.

The minimum positive h=2/h=3 budget becomes a pre-registered diagnostic
ceiling for the next reinjection/continuation gate. Because the isolated stock
endpoint is callback-instrumented, this budget is not a production latency
bound; the next gate must also compare same-work continuation through a
committed token against unmodified stock.

## Resident-expert boundary

This campaign prepares real selected expert tensors and compact CPU/GPU graphs
before warmup.

Therefore it measures:

`RESIDENT_EXPERT_LIVE_HANDOFF_TIMING`.

It does not measure:

- cache misses;
- expert-weight H2D;
- NVMe reads;
- eviction;
- prefetch;
- residency policy.

Those mechanisms remain separate future questions.

## Correct live activation path

The stock context is frozen to `n_gpu_layers=0`, so the captured
`attn_post_norm-0` activation is host-resident.

The timing candidate therefore updates:

- CPU compact input directly from the captured host F32 activation;
- GPU compact input directly from the same host F32 activation.

The older isolated GPU->CPU activation copy is not reused because it models a
different activation authority.

The candidate GPU input update is included in measured latency.

## Two physical h processes

Run h=2 and h=3 separately.

Each process owns:

- one stock llama.cpp context;
- one prepared h-specific Tesy resident executor;
- its own stock comparator;
- its own exact route and activation stream.

This avoids cross-h graph/cache interaction.

## Timing windows

Persist two windows for every stock/serial/async trial.

### Activation-ready window

Start after:

- activation tensor copy to the callback-owned host vector;
- numerical validation against the frozen pre-timing activation.

End at:

- stock callback entry for `ffn_moe_out-0`, or
- synchronized final Tesy GPU aggregation for serial/async.

This contains the stock router plus the selected output path.

### Route-ready window

Start after:

- top-k is validated;
- final routing weights are copied and bitwise validated.

End at the same stock/Tesy endpoints.

For candidates this includes:

- stock scheduler early-stop return;
- host activation updates to CPU/GPU compact inputs;
- serial or async Tesy execution;
- CPU-partial transfer;
- final GPU aggregation.

Rollback is after the endpoint and excluded.

## Validation is outside candidate timing

A source audit caught and corrected an implementation draft where reference
validation ran after early-stop and would therefore have entered candidate
latency but not stock latency.

The final implementation validates:

- activation against the frozen reference before `activation_ready`;
- expert IDs before `route_ready`;
- routing weights before `route_ready`.

Post-return structural checks run only after the endpoint timestamp.

This prevents asymmetric validation overhead.

## Stock endpoint

The stock endpoint is callback entry at `ffn_moe_out-0`, before any output
copy.

The stock scheduler unwind after that callback is deliberately excluded because
a native stock path would continue from the MoE output rather than early-stop.

The external Tesy candidate must pay its final-weights-to-caller early-stop
overhead because the current handoff implementation cannot execute Tesy until
control returns.

This is a conservative asymmetry for the external handoff.

## Triplet schedule

Each h process measures:

- stock;
- serial;
- async.

Warmup:

- 6 triplets;
- all six permutations once.

Measured:

- 81 triplets;
- deterministic cycling through the same six permutations.

Each mode therefore has exactly 81 measured activation-ready samples and 81
route-ready samples.

## Pre/post correctness

Before warmup and after all measured triplets require:

- decode return 0 for stock/handoff early-stops;
- both rollbacks PASS;
- exact token/route/weights;
- activation pair parity;
- activation stability vs pre-timing reference;
- stock-output stability vs pre-timing reference;
- serial-vs-stock PASS;
- async-vs-stock PASS;
- async-vs-serial PASS.

No timing result survives a post-timing exactness failure.

## Decision model

The native tool emits raw samples only.

Python independently recomputes:

- upper median;
- nearest-rank p95;
- min/max/mean;
- budgets;
- ratios;
- decision.

Async GO for each h requires strict stock improvement in median and p95 for
both timing windows.

Async overlap retained additionally requires:

- async route median < serial route median;
- async route p95 <= serial route p95.

Across both h values:

- async survives + retains overlap:
  `LIVE_MOE_HANDOFF_TIMING_GO`;
- otherwise, serial survives for both:
  `LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`;
- otherwise:
  `LIVE_MOE_HANDOFF_TIMING_NO_GO`.

This makes a degraded async mechanism pivot rather than being hidden inside an
overall speedup number.

## Provenance barrier

The timing CLI requires:

`--timing-start-gate FILE`.

The process performs pre-timing correctness/setup and cannot enter warmup until
that gate exists.

The physical runner:

1. starts the process;
2. waits for the pinned `libggml-cuda.so` mapping;
3. SIGSTOPs;
4. verifies executable, exact argv and unique CUDA artifact;
5. creates the timing-start gate;
6. SIGCONTs.

Thus provenance instrumentation precedes all warmup and measured samples.

## Raw and summary schemas

Native raw:

`tesy.live_moe_handoff_timing_raw.v1`.

Independent summary:

`tesy.live_moe_handoff_timing_summary.v1`.

The summary combines h=2 and h=3 and records the chosen execution plus minimum
reinjection budgets.

## Source/static validation completed

**REPRODUZIDO / PASS**:

- timing mode is mutually exclusive with older exactness modes;
- h is restricted to 2 or 3;
- campaign shape is frozen to warmup=6, samples=81, inner=1;
- host activation populates CPU and GPU compact inputs directly;
- candidate endpoint follows synchronized final aggregation;
- rollback occurs after endpoint;
- no candidate output read occurs in the timed trial;
- all six stock/serial/async orders are present;
- reference validation is before timing timestamps;
- native raw contains no decision;
- independent validator defines GO/SERIAL_PIVOT/NO_GO;
- independent validator uses nearest-rank p95;
- provenance gate precedes warmup;
- runner launches separate h=2/h=3 processes;
- build/model/prompt/host/runtime provenance and swap/headroom gates are
  fail-closed.

## Tests not run in this environment

Focused Ruff/compileall/pytest:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Full model-free suite:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Shell syntax:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Native compile:
`NOT_RUN_REFERENCE_HOST`.

Physical live handoff timing:
`NOT_RUN_REFERENCE_HOST`.

## Next gate

If `LIVE_MOE_HANDOFF_TIMING_GO`:

use the minimum async route median/p95 budgets as diagnostic ceilings for a
prospective output-reinjection and continuation gate, and independently require
same-work committed-token non-regression against unmodified stock.

If `LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`:

drop async for the next gate and use the serial budgets.

If `LIVE_MOE_HANDOFF_TIMING_NO_GO`:

kill the external callback handoff mechanism and return to direct graph/backend
integration.

No result here authorizes prefetch.
