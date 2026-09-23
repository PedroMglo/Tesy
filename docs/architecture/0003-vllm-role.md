# ADR-0003 — vLLM is a comparator, not Tesy's primary backend

Date: 2026-09-23
Status: ACCEPTED FOR CURRENT PHASE

## Question

Should Tesy switch from llama.cpp to vLLM because vLLM is generally considered a stronger inference/serving engine?

## Evidence

Current vLLM exposes CPU weight offload through UVA/pinned host memory and a prefetch-based offload path that groups layers and asynchronously moves selected parameter groups.

Its current public configuration supports selective parameter matching, including MoE expert-weight names.

vLLM also has strong MoE/expert-parallel and speculative-decoding infrastructure, including documented speculation support for gpt-oss and Qwen3 MoE families.

However, the current stable offload contract still assumes host-memory backing for the offloaded weights. Dynamic hot/cold MoE expert caching and expert-granular residency are active 2026 RFC/development areas rather than a mature documented >RAM/NVMe path.

## Decision

Keep llama.cpp as the first bring-up backend because:
- it already supports the exact GGUF artefact selected for first bring-up;
- it has a small local deployment surface;
- current source already contains MoE selective-copy logic at `GGML_OP_MUL_MAT_ID`;
- it supports CPU-MoE and lazy/on-demand modes that directly probe the laptop's constrained-memory boundary;
- a first routing trace can be added at a common MoE boundary without adopting a serving stack.

Add vLLM as **B4 comparator** after the first stock llama.cpp smoke and host characterization.

vLLM is especially valuable for:
- comparing CPU-offload policy;
- comparing async prefetch;
- comparing memory overhead;
- later comparing speculative decoding on gpt-oss/Qwen3-MoE.

Do not install vLLM merely to satisfy the matrix if the selected model/hardware combination cannot fit its runtime envelope.

## Falsifier for this decision

Promote vLLM to primary backend if measurements show that:
1. it can load the same or equivalent-quality target under the 8 GiB VRAM / 32 GiB RAM envelope;
2. its existing offload path already exposes enough control/telemetry for Tesy's experiments;
3. its end-to-end latency is materially better or its integration surface is materially safer than the llama.cpp route.

Demote it if installation/runtime overhead or model-format constraints make it ineligible on the reference laptop.

## Claim boundary

This ADR is a backend-selection hypothesis. No vLLM binary has been installed or run on the reference host in this campaign.

Sources:
- https://docs.vllm.ai/en/latest/api/vllm/config/offload/
- https://docs.vllm.ai/en/latest/api/vllm/
- https://docs.vllm.ai/projects/speculators/en/latest/
- https://github.com/vllm-project/vllm/issues/38256
- https://github.com/vllm-project/vllm/issues/57794
