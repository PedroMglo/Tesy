# Live MoE integration source feasibility

Date: 2026-09-24

Branch:
`research/live-moe-integration-feasibility-20260924`

Base:
`research/routed-layer-exactness-20260924`

Prerequisite:
`ROUTED_LAYER_EXACTNESS_GO`.

Evidence class:
`SOURCE_AUDITED / STATIC_FEASIBILITY`.

## Question

What is the smallest live-backend boundary that can test Tesy's exact routed
CPU/GPU expert execution without reimplementing attention, RoPE, KV or the
router?

Re-timing the existing compact replay with real expert IDs and routing weights
has low discriminating value: shape, dtype, top-k and CPU/GPU expert execution
are already represented by the isolated physical campaigns. The missing cost
is integration with the live stock router/backend.

## Scheduler node assignment: STATIC NO-GO

Pinned llama.cpp exposes:

`ggml_backend_sched_set_tensor_backend()`.

That API assigns one graph node to one backend.

GPT-OSS stock MoE uses one `ggml_mul_mat_id` node for each expert projection
over all selected experts. A node-level backend assignment therefore moves the
whole selected-expert op; it cannot place only a subset of routed experts on
CPU while the remainder executes on GPU.

Decision:

`STATIC_NO_GO_SCHEDULER_NODE_ASSIGNMENT_EXPERT_SUBSET`.

## Meta backend expert-axis split: STATIC NO-GO on current pin

The pinned meta backend supports split axes and propagates
`axis >= 2` through `MUL_MAT_ID` when activations are mirrored.

However stock llama.cpp does not use expert-axis splitting for GPT-OSS expert
weights. Its generic FFN split policy uses internal matrix dimensions:

- up/gate expert weights: axis 1;
- down expert weights: axis 0.

Those policies implement tensor parallelism within each expert, not expert
residency.

A hypothetical Tesy split-state callback could request expert axis 2, but the
current pin has no corresponding global-expert-ID remapping/partitioning in
the meta executor.

The CPU `MUL_MAT_ID` implementation defines:

- `n_as = ne02` as the local number of expert matrices;
- every routed ID must satisfy `0 <= id < n_as`;
- the ID is then used directly to select the local expert matrix.

The CUDA MMVQ path likewise uses the supplied ID directly as
`channel_x`.

The meta backend has no special `MUL_MAT_ID` ID-remap path beyond generic
split-state propagation.

Therefore splitting the weight tensor's expert axis into local shards while
leaving authoritative global router IDs unchanged is not a correct expert
residency implementation on this pin.

Decision:

`STATIC_NO_GO_META_EXPERT_AXIS_SPLIT_WITH_GLOBAL_IDS`.

This does not claim that an extended meta backend with explicit ID remapping
could not work.

## Direct graph partition

A correct graph-level implementation would have to preserve one stock routing
calculation and then partition the already selected top-k slots into CPU/GPU
subsets while preserving their final routing weights.

The existing `build_moe_ffn` cannot simply be called once per subset for
GPT-OSS: with `SOFTMAX_WEIGHT` gating, each call would softmax only the
subset's selected weights rather than reuse the authoritative full-top-k
softmax weights.

A correct direct graph patch therefore needs a route-once/expert-execute
separation or an explicit `selected_weights_in` equivalent.

That is feasible design work but materially more invasive than a callback
handoff experiment.

## Cheaper boundary: cb_eval cancellation handoff

The pinned scheduler evaluation callback can cancel graph computation by
returning false.

Pinned `llama_context::decode` propagates
`GGML_STATUS_ABORTED` as return value 2 and removes memory-module entries for
the aborted ubatch position.

This permits a bounded live-router experiment without patching Transformer
math:

1. prefill once with stock llama.cpp;
2. sample the first greedy token;
3. repeatedly decode that same token;
4. observe the exact layer-0 top-k/final routing-weight event;
5. either:
   - stock arm: continue until `ffn_moe_out-0`, timestamp it, then cancel;
   - cancel arm: cancel immediately at the final routing-weight callback;
6. rely on the existing abort rollback before the next repeated trial.

The stock arm measures the live stock MoE segment from final routing weights
to stock `ffn_moe_out-0`.

The cancel arm measures the unavoidable callback/scheduler cancellation
handoff from the same final routing-weight boundary until `llama_decode`
returns.

No Tesy expert compute is executed in this first bound.

## Hard lower-bound decision

Let:

- `T_stock` be the stock route-final-weight -> `ffn_moe_out` latency;
- `T_cancel` be the route-final-weight -> aborted `llama_decode` return
  latency with zero Tesy FFN work.

Any external callback-interception implementation must cost at least
`T_cancel` before adding Tesy's expert execution and any reinjection cost.

Therefore, under an eventual requirement not to regress stock central/tail
latency:

- if `median(T_cancel) >= median(T_stock)`, external interception is a hard
  median no-go even with zero-cost Tesy FFN;
- if `p95(T_cancel) >= p95(T_stock)`, external interception is a hard p95
  no-go even with zero-cost Tesy FFN.

Decision:

- either hard inequality holds:
  `CB_EVAL_INTERCEPT_HARD_NO_GO`;
- both are strictly below stock:
  `CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

A surviving bound is **not** a performance GO. It only authorizes the next
smallest full handoff experiment.

## Why this precedes routed timing

This bound measures integration overhead that the isolated operator benchmarks
cannot see, while avoiding a model-graph patch whose complexity is not yet
justified.

If callback interception is already impossible by the zero-work bound, kill
that integration mechanism and move to a direct graph/backend patch.

If it survives, implement the full route -> capture/handoff -> Tesy
serial/async FFN measurement prospectively.

No prefetch or residency policy is introduced by this source-feasibility
stage.
