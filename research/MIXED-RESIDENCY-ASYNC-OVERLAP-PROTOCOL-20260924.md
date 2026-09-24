# Mixed-residency measured CPU/GPU async-overlap protocol

Date: 2026-09-24

Branch: `research/mixed-residency-async-overlap-20260924`

Parent Tesy commit: `fafa8b9883c818c367c4c32f69b82cf9a82fc049`

Parent Tesy tree: `c26e2256d78f6d6f13f981f21c4c1fb0e129a118`

Pinned llama.cpp commit:
`4e416ee7308dd6b581796f1a6241276cd5982691`

Evidence class: prospective isolated measured-concurrency diagnostic.

## Motivation and admitted prerequisite

The published overlap-bound campaign
`mixed-residency-overlap-bound-20260924T135006Z` measured a
trace-weighted serial diagnostic of 0.5167518333 ms and a derived post-D2H
compute-overlap bound of 0.4039387111 ms. The prospectively frozen 10% gate was
0.46507665 ms, so the persisted decision was
`OVERLAP_IMPLEMENTATION_GO`.

That result justifies implementing one narrow concurrency mechanism. It does
not establish measured async benefit, full-model speedup, cache behavior,
prefetch benefit, or physical PCIe/DRAM/NVMe traffic.

The failed predecessor campaign
`mixed-residency-overlap-bound-20260924T134933Z` remains preserved as
`FAIL_CAMPAIGN_STAGE`; this protocol does not reuse that campaign identity.

## Source feasibility at the pinned backend

At the pinned llama.cpp commit:

- `ggml_backend_graph_compute_async()` delegates to the backend graph
  implementation without the unconditional synchronize performed by
  `ggml_backend_graph_compute()`;
- the CUDA backend enqueues graph work on its stream and
  `ggml_backend_synchronize()` waits with `cudaStreamSynchronize`;
- the CPU backend graph implementation executes synchronously and has no
  backend synchronize callback.

Therefore the smallest mechanism matching the admitted bound is:

1. complete GPU-to-CPU activation copy;
2. enqueue the GPU expert-subset graph with
   `ggml_backend_graph_compute_async`;
3. execute the CPU expert-subset graph synchronously on the calling thread;
4. synchronize the GPU backend;
5. copy the CPU partial output to GPU;
6. execute GPU aggregation synchronously.

No worker thread is required. If the pinned CUDA path internally synchronizes
for a specific kernel path, the measured candidate naturally includes that
loss of overlap.

The runner requires the selected GPU device to advertise
`caps.async=true`. Lack of that capability terminates the campaign.

## Frozen model, workload and routing contract

Reuse the exact Stage B / overlap-bound contract:

- model: `gpt-oss-20b-mxfp4.gguf`;
- model SHA-256:
  `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`;
- layer 0;
- experts 0,1,2,3;
- 32 experts/layer;
- 13,253,760 encoded bytes/expert;
- MXFP4 matrices `[2880,2880,32]`;
- F32 biases `[2880,32]`;
- top-k = 4;
- synthetic uniform mixture weights 0.25;
- 12 CPU threads;
- CPU-backend extra/repack-aware MXFP4 buffer selection with CPU-default
  fallback;
- CPU-default F32 bias buffer;
- CUDA default GPU buffer.

Routing is not changed or predicted. The expert split is the same isolated
h=0..4 diagnostic used by Stage B.

## Same-campaign independent baseline

The serial baseline remains a separate code path and must not call
`ggml_backend_graph_compute_async`.

For h=1..3, serial and async candidate timings are measured in the same
process using the same resident expert tensors and numerical reference. They
are not derived from component sums.

For h=0 and h=4 there is no CPU/GPU compute overlap to apply. They are measured
as serial anchors only and contribute their serial median to both weighted
arms.

No prior campaign timing is substituted for the same-campaign serial
baseline.

## Correctness gate before timing

Build one all-CPU top-4 numerical reference with the same frozen CPU buffer
selection.

Before measured samples:

- execute the serial path and compare with the all-CPU reference;
- for h=1..3, execute the async candidate and compare independently with the
  same reference;
- require finite outputs;
- normalized max error <= 0.005;
- cosine similarity >= 0.9999.

Any serial or async mismatch terminates the campaign before performance
promotion.

This is numerical parity for the isolated operator, not greedy token equality
or distributional equivalence.

## Measurement order

Freeze case order:

`0,4,1,3,2`.

Freeze:

- warmups: 3;
- samples: 21;
- inner repetitions per timed sample: 5.

For each mixed h=1..3 case, warm both paths and then collect paired serial and
async samples. Sample order alternates deterministically:

- even sample index: serial then async;
- odd sample index: async then serial.

Each timed invocation is complete and synchronized before the next invocation.
This pairing reduces fixed order bias without changing the workload.

Record median, p95, min, max, mean, and all 21 sample values for both paths.

## Trace weighting

Use only the admitted grouped histogram:

- h=0: 39;
- h=1: 26;
- h=2: 62;
- h=3: 128;
- h=4: 105;
- total: 360 groups.

Required histogram SHA-256:

`ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

Define:

`weighted_serial = sum(count[h] * serial_median[h]) / 360`

For h=1..3, the candidate term is the measured async median. For h=0/h=4 it
is the same measured serial anchor:

`weighted_async = sum(count[h] * effective_candidate_median[h]) / 360`.

This weighting is a trace-derived arithmetic diagnostic over measured isolated
case medians. It is not a measured full-model latency.

## Prospective decision threshold

Reuse the already preregistered engineering threshold. Do not tune it after
execution:

`weighted_async <= 0.90 * weighted_serial`.

Classify:

- threshold met: `ASYNC_OVERLAP_MEASURED_GO`;
- threshold not met: `ASYNC_OVERLAP_COMPLEXITY_NO_GO`.

The 10% threshold governs whether this concurrency complexity survives the
isolated operator gate. It is not a universal statistical-significance rule
and does not authorize a full-model speedup claim.

## Python environment and no-replace publication

The physical runner must use exactly:

`$TESY_ROOT/.venv/bin/python`.

It records the Python executable, version and imported `tesy` module path and
requires the module to resolve under the current Tesy worktree. Bare system
Python is not admitted for Tesy module execution.

The output root must not exist. A failed root is preserved and never reused.

## Provenance and resource gates

Before timing require:

- clean Tesy worktree and captured Tesy HEAD;
- clean pinned llama.cpp worktree and exact backend pin;
- locked model identity;
- reference-host identity PASS;
- no competing GPU compute process;
- frozen Release/CUDA build:
  - `GGML_CUDA=ON`;
  - `GGML_BACKEND_DL=OFF`;
  - CUDA architecture 89;
  - GCC/G++ 15;
  - pinned nvcc path;
- exact mixed-residency executable SHA-256;
- exact argv;
- exactly one mapped `libggml-cuda.so` with SHA-256;
- admitted histogram SHA-256;
- GPU async capability;
- complete GPU telemetry;
- zero process swap;
- sampled GPU free headroom >= 1024 MiB;
- sampled host MemAvailable >= 2048 MiB.

## Stop conditions

Immediately terminate and preserve FAIL on:

- provenance mismatch;
- model or histogram identity mismatch;
- dirty required worktree;
- missing project `.venv` or wrong imported Tesy path;
- missing GPU async capability;
- serial or async numerical mismatch;
- non-finite output/timing;
- malformed or incomplete raw schema;
- process swap > 0;
- missing GPU telemetry;
- resource-headroom violation;
- OOM, backend error, corruption or unexpected process exit.

Debugging after a failure uses a new campaign identity.

## Deliberate exclusions

This gate does not implement or measure:

- expert prefetch;
- cache insertion/eviction policy;
- predictor accuracy;
- expert-weight transfer;
- speculative decoding;
- full-model generation;
- physical PCIe/DRAM/NVMe traffic;
- bytes per exact committed token.

Prefetch remains explicitly out of scope.

## Next discriminating gate

If the result is `ASYNC_OVERLAP_COMPLEXITY_NO_GO`, stop this concurrency
mechanism and return to the serial mixed-residency architecture before any
prefetch work.

If the result is `ASYNC_OVERLAP_MEASURED_GO`, the next question is whether
the measured operator-level overlap survives integration at the smallest
routed-layer/backend boundary with exact routing and a stock/serial comparator.
That integration requires a separate prospective protocol and campaign.
