# N1 llama.cpp passive routing trace boundary

Date: 2026-09-23
Status: SOURCE_IMPLEMENTED / CI_BUILD_IN_PROGRESS / REAL_MODEL_NOT_RUN

Pinned upstream source:
https://github.com/ggml-org/llama.cpp
commit 4e416ee7308dd6b581796f1a6241276cd5982691

## Source finding

The pinned MoE graph produces the exact selected-expert tensor after top-k routing and names it ffn_moe_topk-<layer>.

The public llama_context_params structure exposes cb_eval through the ggml scheduler callback interface. The callback supports an ask phase so the tracer can request only the selected-expert tensors.

This permits a passive first tracer without changing llama.cpp routing code.

## What the tracer does

native/tesy_llama_trace.cpp:
- links against the exact pinned libllama source;
- can place expert tensors on CPU using the same public tensor-buffer pattern used by the upstream CPU-MoE machinery;
- never changes routing scores, top-k or selected expert IDs;
- disables tracing during prompt prefill;
- forces one input token per subsequent decode call;
- requests only ffn_moe_topk tensors;
- requires I32 expert IDs and one decode column;
- copies only the selected ID tensor to host;
- refuses to replace an existing trace output.

Each raw JSONL record contains:
- decode step;
- input token ID;
- layer;
- ordered selected expert IDs.

It intentionally does not contain expert byte sizes yet. A separate GGUF tensor inventory must define the encoded residency unit before raw traces become simulator input.

## Important limitation

The v1 native tracer tokenizes raw text directly. It is not yet the authoritative GPT-OSS conversational pipeline because GPT-OSS requires Harmony formatting.

Therefore the first real run is an instrumentation/routing diagnostic only.

Before conversational traces become scientific evidence, Tesy must use a pinned Harmony-capable formatting path and prove that trace collection does not change the greedy token trajectory.

## Performance boundary

Callback readback can synchronize work and adds overhead.

Trace timing must never be used as a performance baseline.

Performance baselines remain uninstrumented stock runs with equivalent resource telemetry.

## Physical-host N1 gate

1. Run tesy doctor and preserve the JSON.
2. Verify model filename, exact byte count and SHA-256.
3. Build pinned stock llama.cpp.
4. Run tesy backend probe against that build/source.
5. Build tesy-llama-trace.
6. Execute a bounded 16-token raw trace.
7. Validate it with:
   tesy trace raw-summary TRACE --expected-layers 24 --expected-top-k 4 --expected-experts 32
8. Stop on any missing layer, wrong top-k, out-of-range ID, duplicate record, model error, OOM or swap/resource violation.
9. Derive exact expert tensor inventory only after this gate.

No custom expert cache or predictive scheduler is justified before trustworthy traces exist.
