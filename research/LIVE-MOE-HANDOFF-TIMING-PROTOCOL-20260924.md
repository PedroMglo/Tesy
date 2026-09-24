# Live MoE handoff timing protocol

Date: 2026-09-24

Branch:
`research/live-moe-handoff-timing-20260924`

Prerequisite:
`LIVE_MOE_HANDOFF_EXACTNESS_GO`.

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`.

Evidence class:
prospective resident-expert live-handoff timing diagnostic.

## Objective

Measure whether the already-correct in-process live handoff leaves positive
latency headroom relative to the stock layer-0 MoE segment.

The target stock router remains authoritative. Tesy does not recompute,
predict, reorder, reduce or replace routing.

This gate does not implement output reinjection. Its purpose is to measure the
budget available for a future reinjection gate.

## Admitted correctness prerequisite

The physical exactness campaign established for one repeated layer-0 event:

- decode token `2167`;
- experts `[1, 13, 17, 21]`;
- final routing tensor `ffn_moe_weights_softmax-0`;
- stock-reference and handoff activations bitwise equal;
- h=2 and h=3 serial-vs-stock PASS;
- h=2 and h=3 async-vs-stock PASS;
- h=2 and h=3 async-vs-serial PASS;
- maximum relative error vs stock `5.60445568e-08`;
- cosine 1.0.

Decision:

`LIVE_MOE_HANDOFF_EXACTNESS_GO`.

Timing is forbidden if the same correctness boundary cannot be reproduced
before and after the timing samples.

## Frozen model and workload

Model:
`gpt-oss-20b-mxfp4.gguf`.

SHA-256:
`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.

Size:
`12109564352` bytes.

Prompt:
`benchmarks/prompts/b0-b1-diagnostic.txt`.

Prompt SHA-256:
`431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`.

Stock context:

- `n_gpu_layers=0`;
- context 4096;
- threads 12;
- raw committed prompt;
- greedy first-token sampling;
- layer 0.

Frozen route:

- token `2167`;
- expert IDs `[1, 13, 17, 21]`;
- final routing weights from `ffn_moe_weights_softmax-0`.

Any token, ID or routing-weight drift terminates the campaign.

## What is resident before timing

The campaign is a **resident-expert steady-state** diagnostic.

Before any timing sample:

- real h-specific CPU expert tensors are loaded into the selected CPU compute
  buffer type;
- real h-specific GPU expert tensors are resident in the GPU buffer;
- serial/async compact graphs are allocated;
- routing weights are frozen from the authoritative live route;
- pre-timing exactness passes.

Expert loading, GGUF reads, graph allocation and weight residency setup are not
timed.

Therefore this gate does not measure cache misses, weight transfer, NVMe I/O or
residency-policy cost.

## Separate h=2 and h=3 processes

Run two fresh physical processes:

- h=2: top-k slots 0..1 GPU, slots 2..3 CPU;
- h=3: top-k slots 0..2 GPU, slot 3 CPU.

Each process has its own within-process stock comparator.

This avoids cross-partition graph/cache interaction while preserving the same
model, prompt, route and binary identity.

## Pre-timing exactness

Within each h process, before warmup:

1. run a stock-reference repeated-token arm;
2. early-stop at `ffn_moe_out-0`;
3. require decode return 0;
4. explicitly roll back the repeated KV position;
5. run a handoff arm;
6. early-stop at final routing weights;
7. require decode return 0;
8. explicitly roll back;
9. require exact route/weight equality;
10. require activation numerical parity;
11. run the h-specific Tesy serial path once;
12. run the h-specific Tesy async path once;
13. require serial-vs-stock, async-vs-stock and async-vs-serial PASS.

Frozen numerical thresholds remain:

- relative max <= 0.005;
- cosine >= 0.9999;
- finite values.

The candidate output reads used for parity occur outside timing.

## Prepared candidate input path

The live stock activation is a host F32 vector because the stock context is
frozen to `n_gpu_layers=0`.

For each candidate trial, after the live router early-stops:

- copy the captured activation into the resident CPU compact graph input;
- copy the same captured activation into the resident GPU compact graph input;
- synchronize the required input transfer(s);
- execute the selected serial or async h-specific path;
- synchronize the final GPU aggregation.

Do **not** emulate the older isolated GPU->CPU activation copy. That path
modeled a GPU-authoritative activation; this live boundary has a host
activation captured from the stock CPU context.

The GPU input copy is part of candidate timing.

## Timing endpoints

Use `std::chrono::steady_clock`.

The callback reads and validates the activation before setting the
`activation_ready` timestamp.

The callback reads and validates top-k/final weights before setting the
`route_ready` timestamp.

### Stock arm

After `activation_ready`:

- execute the stock router and stock MoE;
- at callback entry for `ffn_moe_out-0`, timestamp `stock_output_ready`;
- return false to stop the rest of the graph.

The stock endpoint is before any stock-output copy used for later parity.

Record:

`stock_activation_ms = stock_output_ready - activation_ready`.

`stock_route_ms = stock_output_ready - route_ready`.

The scheduler unwind and KV rollback after `ffn_moe_out-0` are not included,
because a stock production path would not early-stop there.

This stock segment is nevertheless **callback-instrumented**: observing
`ffn_moe_out-0` through `cb_eval` can force scheduler synchronization or
graph splitting that an uninterrupted production decode would not require.
Therefore the measured stock-minus-candidate headroom is diagnostic for this
isolated boundary. It is not a physical hard bound on uninterrupted stock
decode latency.

### Serial candidate arm

After `activation_ready`:

- execute the same stock router;
- at final routing weights, timestamp `route_ready`;
- return false;
- wait for `llama_decode` to return 0;
- update resident CPU/GPU compact inputs from the live activation;
- run h-specific serial Tesy FFN;
- synchronize final GPU aggregation;
- timestamp `candidate_output_ready`.

Record activation-ready and route-ready spans to candidate output.

Explicit KV rollback happens only after the endpoint timestamp.

### Async candidate arm

Identical callback and input-transfer boundary, but after early-stop:

- enqueue GPU expert compute;
- execute CPU subset synchronously;
- synchronize GPU;
- copy CPU partial to GPU;
- aggregate on GPU;
- synchronize final output;
- timestamp endpoint.

Rollback again occurs after the endpoint.

## Why early-stop return overhead is included only for Tesy

The external handoff must return control from the stock scheduler before the
current implementation can run the Tesy compact executor.

Therefore the candidate must pay final-weights -> scheduler-return overhead.

The stock comparator does not pay an artificial early-stop unwind after
`ffn_moe_out-0`; its endpoint is the native MoE output itself.

This asymmetry is intentional and conservative for the external handoff.

## Triplet design

Within each h process, measure three modes:

- `stock`;
- `serial`;
- `async`.

Warmup:

- 6 triplet rounds;
- not included in statistics.

The six warmup rounds use all six permutations once:

1. stock, serial, async;
2. stock, async, serial;
3. serial, stock, async;
4. serial, async, stock;
5. async, stock, serial;
6. async, serial, stock.

Measured:

- 81 triplet rounds;
- deterministic cycling through the same six permutations.

Thus each mode has exactly 81 measured samples and rotates across ordinal
positions.

No random ordering is used.

## Statistics

For each h, mode and timing window record the 81 raw samples.

Recompute in an independent Python validator:

- upper median: sorted index `n // 2`;
- nearest-rank p95: `ceil(0.95 * n) - 1`;
- min;
- max;
- arithmetic mean.

Native summary values, if present, are not authoritative.

## Primary measured budgets

For the async candidate define:

`route_budget_median_ms =
stock_route_median_ms - async_route_median_ms`.

`route_budget_p95_ms =
stock_route_p95_ms - async_route_p95_ms`.

Also compute the equivalent activation-ready budgets.

No arbitrary percentage speedup threshold is used.

For the next isolated reinjection experiment, the positive handoff budget is a
prospective diagnostic ceiling: exceeding it kills this external handoff under
the same instrumented comparator. Staying below it is necessary evidence, not
sufficient proof of production non-regression. The reinjection/continuation
gate must independently compare same-work execution through a committed token
against unmodified stock.

## Async decision

For each h, async survives stock only if all are strict:

- async route median < stock route median;
- async route p95 < stock route p95;
- async activation median < stock activation median;
- async activation p95 < stock activation p95.

Async overlap is retained only if:

- async route median < serial route median;
- async route p95 <= serial route p95.

The p95 non-regression requirement preserves the already established async
steady-tail gate.

## Serial fallback decision

For each h, serial survives stock only if all are strict:

- serial route median < stock route median;
- serial route p95 < stock route p95;
- serial activation median < stock activation median;
- serial activation p95 < stock activation p95.

## Campaign decision across h=2 and h=3

If async survives stock **and** retains overlap vs serial for both h=2 and h=3:

`LIVE_MOE_HANDOFF_TIMING_GO`.

If async does not meet that condition, but serial survives stock for both h=2
and h=3:

`LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`.

Otherwise:

`LIVE_MOE_HANDOFF_TIMING_NO_GO`.

A GO or SERIAL_PIVOT only authorizes a reinjection/continuation gate. It does
not establish end-to-end model speedup.

## Post-timing exactness

After all 81 measured triplets, repeat the pre-timing correctness gate in the
same process.

Require again:

- token/route identity;
- activation parity;
- successful rollback;
- serial-vs-stock PASS;
- async-vs-stock PASS;
- async-vs-serial PASS.

Any post-timing mismatch invalidates the timing campaign.

## Build and runtime provenance

Reuse the routed-layer build provenance and bind:

- clean Tesy HEAD;
- clean pinned llama.cpp HEAD;
- mixed-residency source SHA;
- capture source SHA;
- native CMakeLists SHA;
- mixed and capture executable SHAs;
- resolved binary paths.

For each h process:

- freeze exact argv;
- pass a no-replace `--timing-start-gate` path inside that process root;
- wait for the pinned build's `libggml-cuda.so`;
- SIGSTOP the process;
- validate live executable, exact argv and unique mapped CUDA artifact;
- create the timing-start gate only after provenance PASS;
- SIGCONT.

The native process completes its pre-timing exactness/setup and then waits for
the gate before entering the six warmup triplets.

Therefore provenance instrumentation is guaranteed to precede warmup and
measurement. No SIGSTOP occurs after timing starts.

## Resource and thermal gates

Monitor each h process.

Require:

- at least one resource sample per process;
- complete GPU telemetry;
- zero process swap;
- sampled GPU free headroom >= 1024 MiB;
- sampled host MemAvailable >= 2048 MiB;
- finite telemetry.

Persist maximum sampled GPU temperature and power.

This campaign does not infer physical traffic from those samples.

## Output and failure policy

Output root is no-replace.

Persist separately:

- h=2 raw timing;
- h=3 raw timing;
- validated combined summary;
- per-process runtime provenance;
- resources;
- build/input/source provenance.

Any mismatch, wrong identity, non-finite timing, OOM, telemetry failure, swap,
route drift or exactness failure creates/preserves `failure.json`.

Debugging after failure uses a new campaign identity.

## Explicit exclusions

This campaign does not establish:

- output reinjection correctness;
- continuation to a committed token;
- full-layer replacement;
- full-model TTFT, TPOT or tok/s;
- cache hit/miss policy;
- expert miss transfer;
- NVMe traffic;
- physical PCIe or DRAM traffic;
- prefetch;
- speculation;
- novelty.

It is resident-expert live-handoff timing only.

## Next gate

If `LIVE_MOE_HANDOFF_TIMING_GO`:

use the smaller measured async h=2/h=3 route median/p95 budgets as
pre-registered diagnostic ceilings for a prospective
output-reinjection/continuation experiment, while also requiring an independent
same-work committed-token comparison against unmodified stock.

If `LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT`:

drop async from the next reinjection gate and use the serial budgets.

If `LIVE_MOE_HANDOFF_TIMING_NO_GO`:

kill this external handoff boundary and return to direct graph/backend
integration. Do not advance to prefetch.
