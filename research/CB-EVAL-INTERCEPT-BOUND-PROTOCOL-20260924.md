# cb_eval interception zero-work bound protocol

Date: 2026-09-24

Branch:
`research/live-moe-integration-feasibility-20260924`

Prerequisite:
`ROUTED_LAYER_EXACTNESS_GO`.

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`.

Evidence class:
prospective live-backend integration feasibility bound.

## Objective

Test whether an external `cb_eval` interception boundary can possibly beat
the stock routed MoE segment before implementing any Tesy expert handoff.

This is deliberately a zero-Tesy-work lower bound.

It does **not** copy the captured activation, execute CPU/GPU Tesy experts,
reinject a result, advance the token, or measure full-model performance.

## Motivation

Source audit closes two cheaper-looking alternatives on the pinned backend:

- scheduler tensor-backend assignment operates at whole-node granularity and
  cannot split selected experts inside one stock `MUL_MAT_ID`;
- meta-backend expert-axis splitting lacks the global-router-ID to local-shard
  remapping required for exact expert residency.

A direct graph patch remains feasible but requires route-once/expert-execute
separation for GPT-OSS because the stock `SOFTMAX_WEIGHT` path softmaxes the
selected set.

Before buying that complexity, measure the minimum overhead of the public
callback-cancellation boundary.

Source audit:
`research/LIVE-MOE-INTEGRATION-FEASIBILITY-20260924.md`.

## Frozen inputs

Model:
`gpt-oss-20b-mxfp4.gguf`.

Model SHA-256:
`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.

Model size:
`12109564352` bytes.

Prompt:
`benchmarks/prompts/b0-b1-diagnostic.txt`.

Prompt SHA-256:
`431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`.

Backend:
`llama.cpp@4e416ee7308dd6b581796f1a6241276cd5982691`.

Execution:

- `n_gpu_layers=0`;
- context 4096;
- greedy first-token sampling;
- layer 0;
- expected decode input token `2167`;
- expected experts `[1, 13, 17, 21]`;
- routing weight tensor `ffn_moe_weights_softmax-0`;
- six warmup pairs;
- 81 measured pairs.

The token and route identities come from the admitted routed exactness
campaign. Any mismatch terminates this campaign rather than silently timing a
different event.

The `--ngl 0` configuration is intentionally a permissive feasibility
comparator for external interception rather than an optimized stock-performance
claim. A hard no-go against this configuration is strong; a surviving bound is
weak and still requires the full handoff experiment.

## Repeated-event construction

Start one fresh llama.cpp context.

1. Run the frozen prompt normally.
2. Greedily sample the first token.
3. Require that token to be `2167`.
4. Repeatedly call `llama_decode` with that same token.

Every timed trial deliberately aborts the decode.

Pinned `llama_context::decode` maps `GGML_STATUS_ABORTED` to return code
`2` and removes memory-module entries from the aborted ubatch position.

Every trial must therefore return exactly `2`.

The callback verifies that top-k IDs and routing weights are identical to the
first trial for all warmup and measured trials.

This makes the experiment a repeated measurement of one exact routing event,
not a distribution over prompts/tokens/routes.

## Common timing boundary

The callback observes:

- `ffn_moe_topk-0`;
- `ffn_moe_weights_softmax-0`;
- `ffn_moe_out-0`.

Both arms start their timer **after** the routing-weight tensor has been copied
to the host and its route identity has been validated.

Thus callback materialization/read of top-k and routing weights is common
setup and excluded from both measured intervals.

## Stock arm

At the final routing-weight callback:

- start timer;
- return true;
- allow the stock MoE to execute;
- at `ffn_moe_out-0`, timestamp immediately;
- return false to abort the remaining graph.

Define:

`T_stock = route-final-weight callback -> ffn_moe_out-0 callback`.

It measures the stock layer-0 MoE segment under the callback instrumentation
required by this experiment.

It is not total layer latency.

## Zero-work cancel arm

At the same final routing-weight callback:

- start timer;
- return false immediately;
- execute no Tesy FFN work;
- perform no activation copy;
- perform no result reinjection;
- timestamp when `llama_decode` returns `2`.

Define:

`T_cancel = route-final-weight callback -> aborted llama_decode return`.

This is an optimistic lower bound on an external interception design because
a real Tesy handoff must additionally copy/access the activation, execute
experts, return the output and continue model execution.

## Logging control

Pinned llama.cpp logs graph-compute errors when an expected callback abort is
propagated.

Including stderr logging in `T_cancel` would add avoidable I/O and would no
longer be the intended optimistic lower bound.

The benchmark therefore:

1. saves the current llama.cpp global log callback;
2. installs a no-op log callback only for the repeated cancel-bound trials;
3. restores the previous callback immediately after the trials.

This does not change graph computation, abort propagation or rollback
semantics.

## Pairing

Warmup:

- 6 pairs, not persisted into timing statistics.

Measured:

- 81 pairs.

Pair order:

- even pair index: stock, then cancel;
- odd pair index: cancel, then stock.

Serialized identity:

`even_stock_cancel_odd_cancel_stock`.

Each arm therefore contains exactly 81 measured samples.

Statistics:

- upper median: sorted sample index `n // 2`;
- nearest-rank p95:
  `ceil(0.95 * n) - 1`;
- min;
- max;
- arithmetic mean.

## Hard lower-bound decision

The external interception mechanism is impossible to satisfy a no-regression
central/tail latency requirement if cancellation overhead alone consumes at
least the complete stock MoE segment.

Tesy work could in principle overlap part of the abort unwind, but total
external-interception completion still cannot be lower than the zero-work
`T_cancel` boundary itself.

Hard median no-go:

`median(T_cancel) >= median(T_stock)`.

Hard p95 no-go:

`p95(T_cancel) >= p95(T_stock)`.

Decision:

- if either inequality is true:
  `CB_EVAL_INTERCEPT_HARD_NO_GO`;
- only if both are false:
  `CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

Equality is a no-go because a real handoff has strictly positive additional
work.

The Python validator recomputes every statistic and decision from the raw 81
samples. The native persisted decision is not trusted by itself.

## Interpretation

`CB_EVAL_INTERCEPT_HARD_NO_GO` kills the external callback-interception
integration mechanism on this pin for this exact event under the no-regression
criterion. It does not kill direct graph/backend integration.

`CB_EVAL_INTERCEPT_BOUND_SURVIVES` is **not** a speedup result and not an
implementation GO. It only authorizes the next smallest experiment containing
the real activation handoff plus Tesy serial/async FFN execution.

## Provenance

Use the same routed-layer native build provenance as the exactness gate.

Before launch require the build manifest to match:

- current clean Tesy HEAD;
- pinned clean llama.cpp HEAD;
- current routed capture source SHA-256;
- current mixed replay source SHA-256;
- CMakeLists SHA-256;
- capture executable SHA-256;
- mixed executable SHA-256;
- resolved tool paths.

The capture process must additionally pass live:

- `/proc/<pid>/exe` identity;
- exact argv identity;
- executable SHA-256.

No CUDA mapping is claimed for the stock `--ngl 0` process.

## Resource gates

Sample the bound process during execution.

Require:

- at least one resource sample;
- complete GPU telemetry;
- zero process swap;
- sampled GPU free headroom >= 1024 MiB;
- sampled host MemAvailable >= 2048 MiB.

Resources qualify campaign health only. This experiment makes no physical
traffic claim.

## Failure policy

Output root is no-replace.

Any failure preserves `failure.json` with
`FAIL_CAMPAIGN_STAGE`.

Stop on:

- dirty Tesy/llama.cpp checkout;
- wrong HEAD/backend/model/prompt identity;
- stale native build provenance;
- non-physical reference host;
- competing GPU compute process;
- first-token mismatch;
- route-ID/weight drift across trials;
- missing callback tensor;
- any decode return other than `2`;
- non-finite/non-positive timing;
- sample-count/statistic inconsistency;
- live executable/argv mismatch;
- missing resource telemetry;
- process swap/headroom violation;
- OOM or unexpected process exit.

Debugging uses a new campaign identity.

## Explicit exclusions

This bound does not measure:

- Tesy routed FFN latency;
- serial-vs-async Tesy performance;
- full layer latency;
- TTFT, TPOT or tok/s;
- cache policy or hit rate;
- prefetch;
- expert-weight transfer;
- physical PCIe/DRAM/NVMe traffic;
- bytes per committed token;
- run-to-run stability;
- speculation;
- novelty.

## Next gate

If `CB_EVAL_INTERCEPT_HARD_NO_GO`:

kill external `cb_eval` interception and pivot to a direct graph/backend
integration boundary that preserves one authoritative route and reuses the
final routing weights without subset re-softmax.

If `CB_EVAL_INTERCEPT_BOUND_SURVIVES`:

prepare the smallest full handoff experiment:

`stock route -> exact activation handoff -> Tesy serial/async FFN -> output`.

Freeze its median/tail thresholds before physical execution.

Prefetch remains unauthorized in either case.
