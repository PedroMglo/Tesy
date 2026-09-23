# N0 research charter — Tesy

Date: 2026-09-23
Status: exploratory / prospective
Execution class: STATIC + DEVELOPMENT_ONLY until real-model evidence exists

## Problem

Sparse MoE models decouple total model capacity from active parameters per token, but their total expert weights can exceed VRAM and eventually system RAM. Offloading then makes data-dependent expert movement part of the critical path.

Tesy targets a consumer laptop with 8 GiB VRAM, 32 GiB RAM and NVMe. The project asks whether exact MoE inference can exploit session routing locality, heterogeneous compute and speculative work without making cold expert traffic scale with total model size.

## What is already known

The project starts from the assumption that the following are **not** novel by themselves:

- CPU/GPU heterogeneous MoE inference;
- expert offload from host memory;
- expert placement by activation frequency;
- request-level expert tracing;
- expert caching and prefetch;
- dynamic CPU/GPU assignment;
- speculative decoding;
- speculative expert prefetch for MoE;
- analytical/empirical roofline tuning.

See `N0-NOVELTY-OPPORTUNITY-MAP.md`.

## Candidate question

Can a memory-constrained MoE runtime jointly choose:

1. speculative window depth K;
2. the verification working set induced by candidate tokens;
3. NVMe -> RAM admission/prefetch;
4. RAM -> VRAM promotion;
5. CPU-vs-GPU expert execution;

to reduce **cold expert bytes per exact committed token** relative to decoupled policies?

The model's real router and target computation remain authoritative.

## Candidate metric

Define per campaign and per tier:

```text
CEBCT_NVME = expert bytes fetched from storage / exact committed tokens
CEBCT_PCIE = expert weight bytes transferred RAM->GPU / exact committed tokens
```

These are not interchangeable. Requested file bytes, page-cache hits and physical NVMe traffic must also be distinguished by the instrument that can actually observe them.

Secondary metric:

```text
CTCR = exact committed tokens / cold expert residency
```

## Hypotheses

### H0 — trace headroom

Real decode traces have enough temporal/skew locality that a bounded RAM/VRAM expert hierarchy has meaningful headroom over a cache-naive policy.

Exploratory falsifier: even an offline oracle or exact small-instance optimum cannot materially reduce cold bytes under realistic capacities.

No confirmatory percentage is frozen yet; N0 is exploratory and exists to obtain the distributions needed to set one without outcome-shopping.

### H1 — speculative working-set economy

For at least some useful K > 1, exact accepted-token progress can grow faster than the cold distinct-expert working set.

Required later measurement:

```text
accepted_prefix(K)
union_cold_expert_bytes(K)
accepted_prefix(K) / union_cold_expert_bytes(K)
```

Synthetic candidate count is not accepted-token evidence.

### H2 — joint policy value

A causal joint policy for K + multi-tier residency eventually beats strong decoupled baselines on CEBCT and end-to-end latency under the same exact model and hardware envelope.

Baselines must include at least demand-only LRU and the best reproducible existing backend policy available for the selected model.

## Stop / pivot rules

Pivot the relevant mechanism if evidence shows:

- expert working sets exhibit insufficient reuse even for an oracle cache;
- prediction saves fewer bytes than it wastes under the target capacities;
- moving activations to CPU is consistently worse than weight movement at the relevant shapes and there is no overlap route;
- speculation expands the expert union approximately as fast as useful accepted-token progress;
- the proposed policy only wins by changing routing, expert count, quantization, context or target semantics;
- instrumentation cannot distinguish the traffic needed by the claim.

These do not automatically kill MoE inference; they kill the specific hypothesis.

## Phase order

N0. prior-art and opportunity map
N1. model/host inventory and normalized routing traces
N2. causal cache simulator + oracle/headroom analysis
N3. CPU vs transfer-vs-GPU expert crossover
N4. backend integration for demand-only expert residency
N5. causal prefetch and multi-tier promotion
N6. exact K=2 speculative verification + expert-union accounting
N7. joint policy
N8. bounded end-to-end confirmation

Every phase may redirect later phases prospectively.
