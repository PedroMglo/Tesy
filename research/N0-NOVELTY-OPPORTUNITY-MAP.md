# N0 novelty and opportunity map

Cut date: 2026-09-23
Status: literature screening, not exhaustive patent/legal opinion
Decision: **NOVELTY_NOT_ESTABLISHED — GO_TO_TRACE_FEASIBILITY**

## Summary

A generic claim such as "Tesy runs huge MoE models locally using CPU/GPU offload, expert caching, prefetch and speculative decoding" is not defensible as a novel contribution.

Primary prior art identified before implementation:

| Work/system | Relevant capability | Consequence for Tesy |
|---|---|---|
| MoE-Infinity, arXiv:2401.14361 | request-level expert activation tracing, expert caching and prefetch for offloaded MoE | tracing/cache/prefetch are not novelty |
| KTransformers, SOSP 2025/current code | heterogeneous CPU/GPU MoE inference; GPU expert masks; frequency/uniform placement; dynamic expert update | CPU/GPU expert placement and dynamic hot-expert movement are not novelty |
| DALI, arXiv:2602.03495 | workload-aware dynamic CPU/GPU assignment, residual-based prefetch, workload-aware cache replacement on local PCs | dynamic assignment + workload prefetch/cache is not novelty |
| SpecMoEOff, arXiv:2508.21706 | speculative decoding to increase expert workload; CPU/GPU roofline orchestration; auto-tuning | speculation + MoE offload + roofline is not novelty |
| SP-MoE, arXiv:2510.10302 | SD-aware expert offload, speculative expert prefetch, cutoff policy and pipelined I/O | speculative prefetch is not novelty |
| MoE-SpeQ, arXiv:2511.14102 | draft-predicted future experts, proactive prefetch, adaptive amortization roofline | prediction + offload + adaptive speculation is not novelty |

URLs:
- https://arxiv.org/abs/2401.14361
- https://github.com/kvcache-ai/ktransformers
- https://arxiv.org/abs/2602.03495
- https://arxiv.org/abs/2508.21706
- https://arxiv.org/abs/2510.10302
- https://arxiv.org/abs/2511.14102

## Narrow opportunity still worth testing

The remaining candidate is not a component but a decision boundary:

> jointly optimize speculative progress and a true storage -> RAM -> VRAM expert hierarchy by the expected cold expert bytes required per exact committed token.

Questions requiring further citation chasing:

1. Has prior work explicitly optimized the *union* of cold experts induced by speculative candidate windows, instead of treating speculation and residency as separate stages?
2. Has a causal scheduler jointly chosen K, RAM admission, GPU promotion and CPU/GPU execution on a device where the model can exceed RAM?
3. Has progressive promotion (storage -> RAM on moderate confidence, RAM -> GPU on imminent use) been evaluated specifically for exact MoE decode under a committed-token byte objective?
4. Is the objective CEBCT merely a renamed version of an existing traffic/amortization objective in SpecMoEOff/MoE-SpeQ or related work?

Until these questions are answered, no novelty claim is allowed.

## Engineering opportunity independent of novelty

Even if N0 ultimately finds complete prior art, a robust implementation for an 8 GiB VRAM / 32 GiB RAM laptop may still be useful. That would be engineering value, not a scientific novelty claim.

KTransformers' current expert-scheduling tutorial documents a much larger minimum configuration for that path (RTX 4090 24 GB and 256 GB RAM), which makes this laptop an interesting systems corner. That hardware difference does not itself establish novelty.

## Next evidence

Do not build a complex predictive runtime first.

Acquire routing traces from a manageable MoE and quantify:
- frequency/skew;
- per-layer and session working set;
- reuse distance;
- cache headroom;
- K=1/2/4/8 union-of-expert bytes;
- an offline oracle bound alongside causal LRU/LFU-style baselines.

If the oracle has little headroom, stop the caching hypothesis before custom kernels.
