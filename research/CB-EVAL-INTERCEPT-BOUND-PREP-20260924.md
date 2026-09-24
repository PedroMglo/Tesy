# cb_eval interception bound preparation

Date: 2026-09-24

Branch:
`research/live-moe-integration-feasibility-20260924`

Development base:
`45576ea5510ecd5cf7149aff75af4a8f42f40077`

Development base tree:
`0e8ddc52b0548aba5e105d7508230a907d2c61a4`

Evidence class:
`SOURCE_AUDITED / IMPLEMENTED_NOT_RUN / PHYSICAL_NOT_RUN`

## Starting evidence

The previous physical campaign established
`ROUTED_LAYER_EXACTNESS_GO` for one real stock layer-0 decode event:

- callback OFF/ON greedy tokens `[2167, 1309]`;
- stock experts `[1, 13, 17, 21]`;
- final routing-weight tensor `ffn_moe_weights_softmax-0`;
- h=2/h=3 serial-vs-stock, async-vs-stock and async-vs-serial PASS;
- maximum relative error vs stock `5.60445568e-08`;
- cosine `1.0`.

That admits live integration investigation, not routed-layer speed claims.

## Why replay timing is not the next discriminating gate

The compact real-route replay has the same:

- model expert shapes;
- MXFP4/F32 dtypes;
- top-k=4;
- CPU/GPU compact expert execution;
- serial/async overlap mechanism

already exercised by the isolated physical campaigns.

Replacing synthetic expert IDs/weights with one exact route proves correctness,
which is now done, but re-timing that compact graph would mostly remeasure the
same operator mechanics.

The unresolved cost is the live stock-router/backend handoff.

## Source alternatives audited

### Whole-node scheduler assignment

Pinned scheduler API:

`ggml_backend_sched_set_tensor_backend`

assigns one graph node to one backend.

Stock GPT-OSS expert projections are one `MUL_MAT_ID` node across all
selected experts.

Therefore scheduler assignment cannot place a selected subset on CPU and the
rest on GPU.

Decision:

`STATIC_NO_GO_SCHEDULER_NODE_ASSIGNMENT_EXPERT_SUBSET`.

### Meta expert-axis split

Pinned meta-backend split propagation accepts batched matrix splits on
axes >=2.

However:

- stock GPT-OSS expert tensor split configuration is matrix-internal
  tensor-parallelism, not expert-axis residency;
- CPU `MUL_MAT_ID` treats `ne02` as its local expert count and asserts each
  routed ID is within that local range;
- CUDA MMVQ uses the supplied ID directly as the expert/channel index;
- no global expert-ID to local shard-ID remap was found in the pinned meta
  `MUL_MAT_ID` execution path.

A simple axis-2 expert shard would therefore break exact global router IDs.

Decision:

`STATIC_NO_GO_META_EXPERT_AXIS_SPLIT_WITH_GLOBAL_IDS`.

This is a no-go for the unmodified current pin, not for a future meta-backend
extension with explicit ID remapping.

### Direct graph partition

Calling stock `build_moe_ffn` independently for CPU/GPU subsets would alter
GPT-OSS routing weights because `SOFTMAX_WEIGHT` applies its top-k softmax
inside each call.

A correct direct patch therefore requires one authoritative route and reuse of
the final full-top-k weights.

This remains feasible but is more invasive.

## Selected cheap discriminator

Use the public scheduler evaluation callback only as an interception boundary.

The pinned callback can return false and abort graph execution.

Pinned `llama_context::decode`:

- receives `GGML_STATUS_ABORTED`;
- removes memory entries for the aborted ubatch position;
- returns code `2`.

This supports repeated measurement of the same token/route without advancing
that aborted position.

## Implemented lower bound

New opt-in mode in `tesy-routed-layer-capture`:

`--cancel-bound-output`.

Frozen:

- n_gpu_layers=0;
- context 4096;
- warmup pairs=6;
- measured pairs=81;
- expected input token=2167;
- experts=[1,13,17,21];
- final weights callback=`ffn_moe_weights_softmax-0`;
- pair order=`even_stock_cancel_odd_cancel_stock`.

### Stock arm

Timer starts after final routing weights are materialized/validated.

Stock MoE executes.

Timer ends immediately at `ffn_moe_out-0`.

The callback then aborts the remaining graph.

### Cancel arm

Timer starts at the same boundary.

The callback immediately aborts.

Timer ends only when `llama_decode` returns code 2.

It performs:

- zero Tesy expert compute;
- no activation handoff;
- no output reinjection.

Thus it is an optimistic lower bound for an external callback interception
design.

## Expected-abort logging

Pinned llama.cpp emits error logs while propagating an expected callback
abort.

Those logs are avoidable integration I/O and would weaken the lower-bound
interpretation.

The bound therefore saves the current llama log callback, installs a no-op
callback only during the repeated bound trials, then restores the original
logger.

The graph, callback return and rollback semantics are unchanged.

## Hard decision

Let:

- `T_stock` = final routing weights -> `ffn_moe_out-0`;
- `T_cancel` = final routing weights -> aborted `llama_decode` return.

If either:

`median(T_cancel) >= median(T_stock)`

or:

`p95(T_cancel) >= p95(T_stock)`

then:

`CB_EVAL_INTERCEPT_HARD_NO_GO`.

Otherwise:

`CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

A surviving bound is not a speedup or implementation GO.

## Validation implementation

Native output:

- schema `tesy.cb_eval_intercept_bound.v1`;
- classification `MEASURED_CB_EVAL_ZERO_WORK_LOWER_BOUND`.

Python validator:

`src/tesy/cb_eval_intercept_bound.py`

recomputes from raw samples:

- upper median;
- nearest-rank p95;
- min/max/mean;
- cancel/stock ratios;
- hard-no-go booleans;
- final decision.

It also freezes token/route/sample/order identity.

Runner:

`scripts/run_cb_eval_intercept_bound.sh`

is no-replace and fail-closed on:

- source/model/prompt/backend identity;
- physical reference host;
- competing compute process;
- stale native build provenance;
- live executable/argv identity;
- resource telemetry;
- swap/headroom;
- raw/summary validation.

## Source/static validation completed

**REPRODUZIDO / PASS**:

- source audit of scheduler node assignment;
- source audit of stock/meta split configuration;
- source audit of CPU/CUDA `MUL_MAT_ID` global-ID behavior;
- source audit of callback abort propagation/rollback;
- final callback timing boundaries are explicit;
- both arms abort and require decode return 2;
- route identity is required constant across all trials;
- expected abort logging is suppressed only around the bound loop and restored;
- zero-work cancel arm does not call Tesy mixed-residency compute;
- raw decision is independently recomputed by Python;
- Python files introduced by this gate have no intentional performance claim
  beyond the lower-bound definition.

## Tests not run in this environment

Focused Ruff/compileall/pytest:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Full model-free suite:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Shell syntax:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Native compile:
`NOT_RUN_REFERENCE_HOST`.

Physical callback lower-bound campaign:
`NOT_RUN_REFERENCE_HOST`.

## Next gate

If `CB_EVAL_INTERCEPT_HARD_NO_GO`:

kill external callback interception and move to a direct graph/backend design
that exposes route-once plus final selected weights.

If `CB_EVAL_INTERCEPT_BOUND_SURVIVES`:

prepare the full external handoff experiment with activation transfer and Tesy
serial/async expert execution, with thresholds frozen before measurement.

No prefetch work is authorized by this preparation.
