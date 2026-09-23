# N3 trace evidence correction — 2026-09-23

Status: prospective correction before any real-model N3 campaign.

## Preserved context

The existing N3 design remains the source of the passive `ffn_moe_topk` callback boundary. This correction records defects found during adversarial review before using that boundary as model-bearing evidence.

## Defect 1 — `--tokens-out` was parsed but never published

`scripts/compare_trace_exactness.sh` requested `tokens-off.json` and `tokens-on.json` and compared them, but `native/tesy_moe_trace.cpp` never wrote `options.tokens_out`.

Without correction the supposed exactness gate could not succeed for the intended reason.

Correction:
- publish deterministic JSON token-ID evidence with schema `tesy.generated_tokens.v1`;
- use no-replace file creation;
- treat any write/close failure as process failure.

## Defect 2 — generation error could return success

A failure in `llama_token_to_piece` previously broke out of the generation loop and continued to a successful process exit.

Correction: fail nonzero immediately after cleanup.

## Defect 3 — callback failure was not propagated to the application

The ggml scheduler callback return value can stop callback-driven graph iteration without converting that condition into an application-level error code. Therefore returning false on malformed tensor/write failure was not a sufficient fail-closed guarantee.

Correction:
- the trace state records an explicit failure bit;
- the main decode loop checks it after every `llama_decode` call;
- a callback failure terminates the diagnostic nonzero.

## Defect 4 — tracer placement was not safe for the reference 8 GiB GPU

The trace comparison script used `--ngl 99`, while the tracer lacked the stock `--cpu-moe` behavior. The locked gpt-oss-20b GGUF is larger than VRAM, making this a predictable OOM risk rather than a useful experiment.

Correction:
- add `--cpu-moe` to the native tracer using llama.cpp's public tensor buffer override pattern;
- compare trace OFF/ON with the same CPU-MoE placement.

This placement is for diagnostic viability, not a performance baseline.

## Claim boundary

A future PASS of `compare_trace_exactness.sh` establishes only that enabling the passive callback did not change the generated token-ID trajectory under the same tracer code path and placement for that workload.

It does not establish:
- equivalence to every llama.cpp CLI/server path;
- performance neutrality of tracing;
- physical I/O behavior;
- cache benefit;
- model quality;
- >RAM feasibility.

Tracing remains diagnostic-only because callback observation introduces synchronization/readback.
