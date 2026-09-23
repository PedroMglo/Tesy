# N0 amendment — second-pass prior art narrows the claim again

Date: 2026-09-23
Status: prospective clarification
Decision: **BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO**

This document does not erase the earlier N0 map. It records additional prior art found after the first map was committed.

## New findings

### EcoSpec — arXiv:2607.12696

"Less Experts, Faster Decoding: Cost-Aware Speculative Decoding for Mixture-of-Experts" explicitly observes that speculative draft selection changes the union of experts activated during verification. EcoSpec incorporates predicted marginal expert activation cost into draft selection and favors paths that reuse already-covered experts, while retaining the target-model verification rule.

This directly overlaps the initial Tesy idea of expert-union-aware speculative proposal selection.

Source:
https://arxiv.org/abs/2607.12696

### AcceptMoE — arXiv:2608.02989

AcceptMoE explicitly separates verified-token count, activated-expert union size and expert-weight traffic. Its verifier-side expert selection is commitment/residency-aware. Importantly, its eligibility restriction changes the target distribution, which is outside Tesy's exact-target rule, but the cost observation itself is prior art.

Source:
https://arxiv.org/abs/2608.02989

### llama.cpp expert-cache work

Current llama.cpp already supports:
- `--cpu-moe`;
- `--n-cpu-moe`;
- tensor overrides;
- mmap/load modes;
- `--lazy-mode` for on-demand rows/tensors in supported cases.

Recent 2026 RFC/PR work also implements GPU-resident caches for CPU-offloaded experts, including persistent slot-pool/LRU designs. These are active/recent and must be treated as baselines, not rediscovered.

Sources:
- https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md
- https://github.com/ggml-org/llama.cpp/discussions/24528
- https://github.com/ggml-org/llama.cpp/discussions/28248
- https://github.com/ggml-org/llama.cpp/issues/20757

### MoE Expert Cache research preview

The MIT-licensed repository `CAN230921/moe-expert-cache` provides:
- a pinned llama.cpp patch series;
- Qwen3-MoE route tracing;
- demand-mmap oversubscription;
- cache-policy replay;
- retained negative expert-cache evidence;
- controlled >RAM proxy experiments.

Its retained evidence reports a demand-mmap mechanism benefit under an 8 GiB cgroup proxy for Qwen3/Qwen3.5, while explicitly noting that physical SSD traffic was not established.

Source:
https://github.com/CAN230921/moe-expert-cache
Observed public commit during this review:
`7bbd3ea8e3bff8806fb4d24aa712d22662bd199f`
License: MIT.

### Other multi-tier implementations

Public systems/research implementations also exist that combine storage, DRAM and accelerator expert residency. Their claims require independent verification before use as evidence, but they further weaken any generic "three-tier MoE cache" novelty claim.

## Consequence

The following are now explicitly **not candidate novelty claims**:

- expert-union-aware speculative scheduling in general;
- cache-residency-aware speculative cost in general;
- GPU hot-expert caches for CPU-offloaded MoE;
- demand-mmap oversubscription in general;
- NVMe/RAM/VRAM expert hierarchy in general.

Tesy must not relabel these as inventions.

## What remains worth doing

Tesy continues for two reasons:

1. **Engineering/reproducibility:** determine what actually works on the unusually constrained reference laptop (8 GiB VRAM, 32 GiB RAM), using exact routing and explicit evidence.
2. **Opportunity discovery:** measurements may expose a narrower unsolved boundary — for example a causal exact policy specific to severe >RAM operation, a different placement objective, or a backend mechanism not covered by existing work.

The project is allowed to end with "existing method X is best on this host." That is a valid result.

## Immediate pivot in implementation order

Do not implement a custom expert cache yet.

First reproduce/compare:
1. stock llama.cpp automatic placement;
2. stock `--cpu-moe` / `--n-cpu-moe`;
3. stock supported lazy/on-demand mode where applicable;
4. a reproducible external demand-mmap/trace baseline if model architecture and license permit;
5. only then a Tesy-specific mechanism if a measured gap remains.

## Claim boundary

Current status:

```text
Novelty: NOT ESTABLISHED
Broad architecture novelty: NO-GO
Useful constrained-hardware engineering: OPEN
Narrow future scientific contribution: OPEN / UNKNOWN
```
