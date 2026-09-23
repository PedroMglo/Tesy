# N3 native MoE routing trace design

Date: 2026-09-23
Status: IMPLEMENTED_SOURCE / BUILD_VALIDATION_PENDING_AT_COMMIT

## Source finding

At llama.cpp pin `4e416ee7308dd6b581796f1a6241276cd5982691`:

- the common MoE graph creates `ffn_moe_topk-<layer>`;
- GPT-OSS uses the common `build_moe_ffn` path;
- selected expert products use `build_lora_mm_id -> ggml_mul_mat_id`;
- `llama_context_params.cb_eval` is public;
- the scheduler makes requested callback tensors available after the producing graph segment is synchronized.

Therefore Tesy does not need to patch the router or infer expert IDs from logits.

## Implementation

`native/tesy_moe_trace.cpp` links against the exact pinned stock llama.cpp source and installs a callback that requests only tensors named `ffn_moe_topk-<layer>`.

Raw output schema:

`tesy.llama_moe_topk.v1`

Each line records:
- a monotonically derived `graph_seq`;
- layer;
- number of tokens represented by the top-k tensor;
- number of selected experts per token;
- exact selected expert IDs.

No activations, prompts or logits are written to the trace.

## Important performance boundary

The eval callback deliberately requests a tensor after compute. The current llama.cpp scheduler synchronizes the producing backend before invoking the data callback.

Therefore **the tracer changes synchronization behavior and is diagnostic-only**.

Its wall time, token/s, PCIe behavior and overlap are not valid production-performance measurements.

The stock binary remains the performance baseline.

## Graph sequence

The callback API does not expose absolute token positions. Tesy increments `graph_seq` when the observed MoE layer index resets/decreases.

This is sufficient to identify evaluation groups under the initial single-sequence campaign.

It does not silently label every graph as a committed decode token.

The raw analyzer reports `n_tokens` for each graph. Campaign logic may classify the initial multi-token prompt evaluation and later single-token decode evaluations only after the workload/ubatch contract is frozen.

## Byte accounting

The raw trace contains expert IDs, not encoded expert-byte footprints.

This intentionally prevents the project from fabricating byte counts before a GGUF tensor inventory maps each (layer, expert) to its actual encoded spans.

N3 answers locality/reuse questions in expert-count space first. A later inventory stage adds byte weighting.

## Exactness check required on physical host

For the same pinned stock source and model:
1. run stock greedy smoke;
2. run tracer greedy smoke with identical prompt/settings;
3. compare committed token IDs/output hash;
4. only if equal, use routing IDs diagnostically.

A trace mismatch is a FAIL of the tracing boundary.

## Model applicability

Because the hook observes the common `ffn_moe_topk` graph tensor rather than a Qwen-specific router, the design is intended to cover GPT-OSS and other llama.cpp MoE architectures using `build_moe_ffn`.

That portability is source-derived and must be validated with each admitted model.
