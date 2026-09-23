# ADR-0001 — backend strategy

Date: 2026-09-23
Status: ACCEPTED FOR BRING-UP; revisit after N2 evidence

## Context

Tesy needs exact routing/token semantics and access to expert residency decisions. Reimplementing a complete model stack would create a large correctness surface unrelated to the research question.

Current relevant backends include llama.cpp/GGML and KTransformers/SGLang.

## Decision

1. Use a **stock llama.cpp build** as the first portable baseline and model-bring-up path for GGUF models.
2. Keep Tesy's Python layer limited to host inspection, model admission, trace/simulation/planning, experiment orchestration and reporting.
3. Do not put per-expert hot-path callbacks through Python.
4. Before implementing native expert residency, inspect the selected llama.cpp model implementation and scheduler to find the smallest C/C++ hook that can expose exact router decisions and expert-weight residency.
5. Keep the stock binary and any Tesy-patched build independently runnable.
6. Treat KTransformers as a strong comparator/reference and potential future backend, not as an automatic dependency.

## Why not adopt KTransformers immediately?

Current KTransformers supports CPU/GPU expert masks, several placement strategies and dynamic expert updates. Those capabilities are valuable prior art and a future baseline.

However, its documented expert-scheduling path targets substantially larger host resources than the reference laptop, and bringing SGLang/KT into the first experiment would confound the basic question of whether the trace/cache headroom exists.

This is not a rejection of KTransformers. N2/N3 evidence may justify switching backend.

## Why llama.cpp first?

- broad GGUF support and consumer-hardware deployment;
- straightforward stock baseline;
- gpt-oss and Qwen MoE families are available in GGUF ecosystems;
- lower integration burden for the first real-model trace experiment;
- lets Tesy measure the reference laptop before adding a larger serving stack.

## Constraints

No performance claim is inherited from upstream.
No Tesy-optimized runtime exists until a native residency path actually changes physical expert movement.
A launcher around stock llama.cpp remains a baseline, not the Tesy contribution.

Before any patch:
- pin an exact upstream commit;
- document the source boundary;
- compile and run stock on the physical host;
- identify exact expert tensor layout and router boundary;
- define an independent exactness test;
- freeze a minimal ABI for trace/residency events.
