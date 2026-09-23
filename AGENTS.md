# Tesy agent contract

Tesy researches and builds memory-constrained local inference for sparse/MoE language models.

## Truth before agreement

Do not protect the owner's ideas, previous design decisions, sunk cost, or your own code. A negative result is evidence. State measured, reproduced, estimated, inferred, hypothesis, diagnostic, and unknown separately.

Do not claim novelty because components are combined. Prior art must be searched before a scientific claim. A useful integration may remain valuable even when it is not novel.

Do not alter thresholds, baselines, workloads, model identity, or claim scope after observing a result to manufacture PASS. Material scientific changes are prospective and documented before the measurement they affect.

## Reference machine

The intended physical host is a Linux laptop with:
- AMD Ryzen AI 9 HX 370, 12 cores / 24 threads;
- NVIDIA RTX 4060 Laptop GPU, 8 GiB VRAM;
- 32 GiB system RAM;
- NVMe storage.

This is a target configuration, not permission to invent live state. Before hardware-bearing claims, verify the actual host, GPU, RAM/swap, storage/mounts, driver/CUDA, processes, power/thermal state, branch and exact binaries. VM/container results do not qualify the physical laptop.

## Core correctness rule

The model's exact routed computation is the authority for committed tokens.

A predictor may prefetch, rank, place or propose. It may not silently change router decisions, drop experts, reduce top-k, replace a missing expert, truncate context, alter quantization, or confirm tokens.

Bitwise equality, numerical parity, greedy token equality and distribution-preserving stochastic sampling are different claims. Name the exact contract being tested.

## Research direction

The current candidate question is narrower than generic MoE offload:

Can speculation depth, future expert working set, and NVMe/RAM/VRAM residency be scheduled jointly so that cold expert bytes per exact committed token decrease on severely constrained local hardware?

This is a hypothesis, not an established novelty claim.

Primary exploratory metrics:
- NVMe expert bytes / committed token;
- RAM-to-GPU expert bytes / committed token;
- committed tokens / cold expert residency;
- expert-cache hit rate and reuse distance;
- speculative expert-union bytes;
- wasted-prefetch bytes;
- TTFT, TPOT/tokens/s and tail latency;
- RAM, VRAM, swap and thermal state.

## Architecture discipline

Prefer a mature backend for tokenizer, model graph, attention, KV, sampling and exact routing. Do not reimplement a complete Transformer merely to experiment with expert residency.

Keep a stock baseline independent from any patched backend.

Start with demand-only behavior and simple policies. Add prediction, speculation, low-rank caches, custom kernels or dynamic quantization only when a cheaper experiment justifies them.

Roofline/capacity analysis precedes expensive model runs. Exactness precedes timing. Simulated bytes are never relabelled as physical traffic.

## Experiments

Before confirmatory execution freeze:
- commit/tree and clean worktree;
- model/tokenizer/template/revision/checksums;
- backend/toolchain/binary identity;
- workload, context, seeds and generation policy;
- baseline and candidate;
- metrics, thresholds and stop conditions;
- output root and publication policy.

A mismatch, corruption, OOM, retry, non-finite value, incomplete provenance, missing required telemetry or resource violation ends that campaign. Debugging uses a new campaign identity; old failures remain.

Use small tests first:
schema -> synthetic/fault -> simulator -> operator -> routed layer -> small real model -> chat -> bounded benchmark -> sustained/scale.

## Git and repository boundaries

Development occurs on dedicated branches. Do not merge automatically and do not force-push. Keep commits intentional.

Do not commit model weights, build products, caches, raw traces containing private prompts, or generated large artefacts.

External dependencies must be pinned before measurements. Do not silently modify a shared installation from another project.

Tesy is repository-independent. Do not reference, import, build, publish, tag or depend on the owner's unrelated repositories (including `PedroMglo/ai-local-runtime-kit` and MOSAIC-LLM) unless the user explicitly requests that integration and an ADR records the exact reason, provenance, license and rollback plan.

Do not add Dockerfiles, Compose definitions, devcontainers, GHCR/package publishing, container images or container-based runtime dependencies merely for convenience. Containerization requires an explicit Tesy ADR and must not reuse images owned by unrelated projects.

## Models

Never download large models automatically. Maintain `MODELOS_A_INSTALAR.md` and a machine-readable lock/candidate manifest. The user decides when to download weights.

A model is not supported merely because its architecture name appears in code. Track implementation and validation status separately.

## Communication

Lead with current result/state. For every material phase leave an auditable record under `research/`: objective, base commit/tree, evidence class, alternatives, decision, tests/NOT_RUN, failures, limitations and next discriminating gate.
