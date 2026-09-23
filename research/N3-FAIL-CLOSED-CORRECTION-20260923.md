# N3 fail-closed trace correction

Date: 2026-09-23
Status: prospective correction before the first real-model paired trace campaign.

## Background

The foundation N3 tracer already introduced passive observation of the exact ffn_moe_topk tensor and later added token-ID output for trace OFF/ON comparison.

Adversarial review found three remaining implementation risks before running the locked model.

## 1. Callback errors were not application errors

The ggml scheduler callback can stop callback-driven graph iteration when the data callback returns false, but that does not by itself give the tracer a robust application-level failure code.

Correction: trace state carries an explicit failed flag. Malformed top-k tensor, invalid stride or trace write/flush failure sets the flag, and the main loop terminates nonzero immediately after llama_decode.

## 2. token-to-piece failure was fail-open

The previous tracer broke the generation loop on llama_token_to_piece failure and could then return success.

Correction: this is now a nonzero process failure.

## 3. The paired diagnostic placement could exceed 8 GiB VRAM

The paired script used ngl=99 and the native tracer lacked CPU-MoE placement. The locked GGUF is larger than reference VRAM, so an OOM would be predictable rather than discriminating.

Correction: the tracer accepts --cpu-moe using llama.cpp's public expert tensor buffer override. The paired trace OFF/ON gate uses the same CPU-MoE placement in both arms.

This does not establish that CPU-MoE is the fastest placement. It only makes the tracing diagnostic admissible on the constrained host without changing expert routing semantics.

## Claim boundary

A future PASS of the paired trace gate means only that enabling the passive callback preserved the generated greedy token-ID trajectory under the frozen raw-prompt tracer path and same placement.

It does not establish performance neutrality, Harmony/chat equivalence, physical I/O, cache benefit or >RAM feasibility.
