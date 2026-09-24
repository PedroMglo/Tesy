# Routed-layer exactness preparation

Date: 2026-09-24

Branch:
`research/routed-layer-exactness-20260924`

Development base:
`b4f8e6f6123313604d5dda321d01452faff3957d`

Development base tree:
`eb35e7cf38a0a63ff706ecf7eaf76e6ce4b5096e`

Evidence class:
`SOURCE_AUDITED / IMPLEMENTED_NOT_RUN / PHYSICAL_NOT_RUN`

## Result leading into this gate

The isolated async mechanism has passed two physical gates:

- `ASYNC_OVERLAP_MEASURED_GO`;
- `ASYNC_STEADY_TAIL_GO`.

The 81-pair tail gate did not reproduce the earlier serial-to-async
amplification and passed the prospectively frozen h=2/h=3 steady median and
p95 limits.

This justifies a real-router correctness gate. It does not justify
routed-layer timing without first proving the replay math against stock output.

## Cheapest discriminating experiment

Do **not** patch the live llama.cpp model graph yet.

Instead, use stock llama.cpp as the routing and numerical authority:

1. run the committed prompt with callback OFF;
2. run it again with callback ON;
3. require identical two-token greedy trajectories;
4. during one layer-0 decode event capture the exact stock activation, top-k,
   final routing weights and MoE output;
5. replay that exact event with the existing Tesy compact serial and async
   paths for controlled h=2 and h=3 partitions;
6. compare both replay outputs numerically with stock `ffn_moe_out-0`.

This isolates routing/replay correctness before buying scheduler/model-graph
integration complexity.

## Pinned source audit

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`.

GPT-OSS uses `LLM_ARCH_OPENAI_MOE`.

At each layer the pinned graph exposes:

- `attn_post_norm-<layer>` immediately before `build_moe_ffn`;
- `ffn_moe_topk-<layer>` after stock top-k selection;
- `ffn_moe_weights_softmax-<layer>` after top-k softmax for
  `SOFTMAX_WEIGHT` gating;
- `ffn_moe_weights_scaled-<layer>` only when
  `w_scale != 0.0f && w_scale != 1.0f`;
- `ffn_moe_out-<layer>` after expert weighting and aggregation.

Therefore the final routing weight tensor is:

- scaled if the scaled callback stage is emitted;
- otherwise the softmax tensor.

The pre-softmax `ffn_moe_weights-0` tensor is not admitted.

The stock expert branch performs the same operation order used by the compact
replay:

- gate/up expert matmul;
- expert biases;
- OAI SwiGLU with alpha 1.702 and limit 7.0;
- down expert matmul;
- down bias;
- routing-weight multiply;
- expert sum.

## Implementation

### Stock capture

New target:

`tesy-routed-layer-capture`.

It uses stock llama.cpp and does not replace any model computation.

Callback is installed only on the ON run and remains disabled during prompt
prefill. It is enabled only for the one-token decode after the first greedy
token is sampled.

Captured layer-0 tensors:

- `attn_post_norm-0`;
- `ffn_moe_topk-0`;
- `ffn_moe_weights_softmax-0`;
- optional `ffn_moe_weights_scaled-0`;
- `ffn_moe_out-0`.

It writes raw F32 activation/output files plus strict metadata.

### Compact replay

`tesy-mixed-residency` gained an opt-in
`--routed-exactness` mode.

The existing benchmark mode is unchanged by default.

Routed mode:

- reads exact captured activation;
- reads exact stock output reference;
- preserves exact top-k slot order;
- accepts the exact captured routing weights instead of synthetic 0.25;
- executes controlled h=2/h=3 prefix-GPU partitions;
- runs serial once and async once;
- performs no timing;
- fails immediately on any numerical parity mismatch.

The controlled split is explicitly not a cache/residency policy.

## Numerical gate

Reuse existing frozen operator parity:

- relative max <= 0.005;
- cosine >= 0.9999.

For each h=2/h=3 require:

- serial vs stock PASS;
- async vs stock PASS;
- async vs serial PASS.

OFF/ON token IDs must also match exactly.

Only then:

`ROUTED_LAYER_EXACTNESS_GO`.

## Provenance hardening

New bootstrap:

`scripts/bootstrap_routed_layer_exactness.sh`.

Its build sidecar binds:

- clean Tesy HEAD;
- llama.cpp HEAD;
- both native source SHA-256 values;
- CMakeLists SHA-256;
- both executable SHA-256 values;
- resolved tool paths.

New generic stock-process provenance probe:

`tesy.process_identity`

checks live executable bytes and exact argv.

The h=2/h=3 CUDA replays reuse
`tesy.mixed_residency_provenance`.

Because the correctness replay can finish quickly, the runner waits for the
CUDA library mapping, SIGSTOPs the process, validates live executable/argv/CUDA
mapping, then SIGCONTs it. No latency is measured, so this provenance
instrumentation cannot contaminate a performance result.

## Model-free source/static checks completed

**REPRODUZIDO / PASS**:

- required C++ include dependencies for `PRId*` and
  `istreambuf_iterator` are explicit;
- unused capture constant removed before native compile;
- callback tensor names match pinned source callback names;
- stock capture only enables payload capture on the decode event;
- compact routed path contains no `measure` or `measure_paired`;
- exact real routing weights flow into compact expert weighting;
- serial/async/stock comparisons are all explicit;
- controlled partition identity is serialized;
- runner contains no median/p95/speedup output;
- runner is no-replace and uses the project `.venv`;
- model, prompt, llama pin, physical-host, build and resource gates are
  fail-closed;
- Python files introduced by this gate have no lines over 100 characters.

## Tests not run in this environment

Final focused pytest:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Full model-free suite:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Shell syntax:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Native CPU/CUDA compile:
`NOT_RUN_REFERENCE_HOST`.

Physical routed-layer exactness campaign:
`NOT_RUN_REFERENCE_HOST`.

## Failure boundary

Any token, captured tensor, routing identity, numerical, provenance, resource
or process failure terminates and preserves a new campaign root.

A failed exactness campaign does not authorize timing or prefetch.

## Next gate

If physical exactness returns `ROUTED_LAYER_EXACTNESS_GO`, freeze a separate
routed-layer timing protocol with preregistered median/tail thresholds.

If it fails, diagnose or kill this replay/integration boundary.

No routed-layer timing, prefetch, cache policy or full-model speedup experiment
was run while preparing this branch.
