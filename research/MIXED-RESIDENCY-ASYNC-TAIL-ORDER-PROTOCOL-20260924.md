# Mixed-residency async order-conditioned tail protocol

Date: 2026-09-24

Branch:
`research/mixed-residency-async-tail-order-20260924`

Base evidence:
`research/MIXED-RESIDENCY-ASYNC-OVERLAP-RESULT-20260924.md`

Classification:
prospective isolated tail/order diagnostic.

## Question

Does the async mechanism retain its central-latency benefit without an
unacceptable steady-state p95 regression once serial-to-async comparator
transitions are separated from async-after-async observations?

This gate is cheaper than routed-layer integration and exists because the
published 21-sample campaign showed large h=2/h=3 aggregate p95 values that are
strongly associated post hoc with serial-to-async sample order.

## Mechanism

Do not change the native scheduling mechanism.

Reuse exactly:

`post_d2h_gpu_enqueue_cpu_sync_gpu_wait`.

Reuse the paired sample order:

`even_serial_async_odd_async_serial`.

The existing runner is parameterized prospectively with:

- `TESY_ASYNC_SAMPLES=81`;
- `TESY_ASYNC_TAIL_ORDER=1`.

The dedicated operator entrypoint is:

`scripts/run_mixed_residency_async_tail_order.sh`.

It invokes the same async binary, provenance gates, parity checks, resource
monitoring and trace-weighted median calculation as the admitted async
campaign.

## Frozen identities

Reuse:

- gpt-oss-20b MXFP4 GGUF;
- model SHA-256
  `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`;
- llama.cpp
  `4e416ee7308dd6b581796f1a6241276cd5982691`;
- layer 0;
- experts 0,1,2,3;
- top-k 4;
- 12 CPU threads;
- 3 warmups;
- 5 inner repetitions per timed block;
- admitted histogram SHA-256
  `ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

Routing remains synthetic/frozen exactly as in the isolated async gate. This
campaign does not claim a committed-token routed-layer measurement.

## Samples and order conditioning

Freeze 81 paired samples.

Because warmups end with async and timed pairs alternate deterministically:

- `async_after_serial = async_samples[0::2]`: 41 samples;
- `async_after_async = async_samples[1::2]`: 40 samples;
- `serial_after_async = serial_samples[1::2]`: 40 samples;
- `serial_after_serial = serial_samples[2::2]`: 40 samples.

Sample 0 serial is excluded from steady serial because it follows the final
async warmup.

Use the same upper-median convention as the native benchmark and nearest-rank
p95:

`index = ceil(0.95 * n) - 1`.

With n=40, p95 is no longer a single maximum.

## Prospective gate

h=1 is a diagnostic control only.

Gate h=2 and h=3 independently.

For both h=2 and h=3 require:

1. steady async median retains at least 10% improvement:

`AA_median <= 0.90 * SS_median`;

2. steady async p95 regresses by no more than 10%:

`AA_p95 <= 1.10 * SS_p95`.

The 10% median threshold reuses the already preregistered engineering budget.
The symmetric 10% p95 budget is frozen before this new campaign and does not
favor the post-hoc h=3 observation, which was 10.8% worse in the small n=10
source subset.

Decision:

- both gates pass for h=2 and h=3:
  `ASYNC_STEADY_TAIL_GO`;
- otherwise:
  `ASYNC_STEADY_TAIL_NO_GO`.

Also record, without making it a pass criterion:

`SA_p95 / AA_p95`

as the serial-to-async transition amplification diagnostic.

## Correctness and resources

Reuse the existing async campaign fail-closed gates:

- serial parity PASS against all-CPU reference;
- async parity PASS for h=1..3;
- finite outputs/timings;
- exact executable/argv/mapped CUDA provenance;
- native build/source sidecar PASS;
- project .venv provenance PASS;
- physical reference host PASS;
- no competing GPU compute process;
- zero process swap;
- complete GPU telemetry;
- >=1024 MiB GPU free headroom;
- >=2048 MiB MemAvailable;
- no-replace campaign root.

Any execution/provenance/resource failure preserves FAIL and requires a new
campaign identity.

A valid `ASYNC_STEADY_TAIL_NO_GO` is a successful diagnostic, not an
execution failure.

## Alternatives and next gate

If `ASYNC_STEADY_TAIL_NO_GO`:

- do not integrate async overlap into the routed layer;
- investigate or kill the mechanism before prefetch.

If `ASYNC_STEADY_TAIL_GO`:

- proceed to a separate prospective routed-layer/backend integration gate;
- preserve exact router output;
- compare serial and async at the same routed layer;
- preregister its own median and tail acceptance criteria before execution.

## Claim boundary

This campaign measures only order-conditioned latency of the isolated
real-weight mixed FFN.

It does not establish:

- routed-layer latency under live router decisions;
- full-model latency/throughput;
- cache or prefetch benefit;
- physical PCIe/DRAM/NVMe traffic;
- bytes per exact committed token;
- run-to-run stability;
- novelty.
