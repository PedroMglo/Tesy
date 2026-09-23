# B2 static result — llama.cpp lazy mode does not cover locked gpt-oss experts

Date: 2026-09-23
Classification: STATIC_SOURCE_RESULT
Decision: `STATIC_NO_GO_B2_GPTOSS_EXPERT_LAZY`

## Boundary

Backend:
`ggml-org/llama.cpp@4e416ee7308dd6b581796f1a6241276cd5982691`

Target:
locked `gpt-oss-20b-mxfp4-gguf`.

Question:

> Does the pinned stock `--lazy-mode` provide on-demand expert-weight reading
> suitable as a gpt-oss expert oversubscription baseline?

## Source evidence

The public lazy-mode contract states that rows are read on demand only for
tensors **marked by the architecture**. In the model loader this is represented
by `TENSOR_READ_LAZY`.

A repository-wide source search at the pinned commit finds architecture uses of
`TENSOR_READ_LAZY` for specific per-layer embedding tensors such as Gemma4
and Qwen4exp.

In `src/models/openai-moe.cpp`, the gpt-oss expert tensors are created with
flags `0`:

```text
ffn_gate_exps weight ... flags 0
ffn_down_exps weight ... flags 0
ffn_up_exps   weight ... flags 0
ffn_gate_exps bias   ... flags 0
ffn_down_exps bias   ... flags 0
ffn_up_exps   bias   ... flags 0
```

They are not marked `TENSOR_READ_LAZY`.

Relevant pinned sources:
- `src/llama-model-loader.h`
- `src/llama-model-loader.cpp`
- `src/models/openai-moe.cpp`
- `include/llama.h`
- `tools/cli/README.md`

## Decision

For this exact backend pin and locked gpt-oss target:

```text
STATIC_NO_GO_B2_GPTOSS_EXPERT_LAZY
```

Do not spend a model-bearing campaign testing `--lazy-mode` as if it were a
gpt-oss expert cache/oversubscription mechanism.

This does **not** mean:
- mmap/page-cache behavior is irrelevant;
- llama.cpp cannot run the model with CPU-resident experts;
- future llama.cpp commits cannot add lazy expert support;
- other architectures do not use lazy tensors;
- demand-mmap or another external expert mechanism is disproved.

Any future backend pin that changes expert tensor flags reopens B2
prospectively.

## Scientific value

This is exactly why Tesy probes implementation semantics before performance.
A CLI flag alone is not evidence that the physical boundary required by an
experiment exists.
