# N0 — causal residency foundation

Date: 2026-09-23, Europe/Lisbon. Classification: DEVELOPMENT_ONLY.
Base: empty GitHub repository, no branch/HEAD/tree/AGENTS/submodules available.
Remote issue #1 already tracks the task. A previous claimed local worktree was
not present in this session; no previous code is represented as recovered.
Local work starts on research/tesy-n0-foundation-20260923, not main.

## Decision frozen before implementation

Do not implement a speculative optimizer on assumed acceptance. First deliver
strict traces, metadata-only GGUF inspection, separate two-tier byte accounting,
a causal demand/prefetch baseline, offline union analysis, an actual bounded
native CPU residency primitive, and a clearly identified stock CLI handoff.
Native tests use synthetic F32 experts, not quantized production MoE inference.

Use llama.cpp as the first external baseline, keep its unmodified semantics.
Do not fork a Transformer. Dynamic quantized MoE integration is a later milestone,
not completed by this phase. Qwen3-30B-A3B-Instruct-2507 Q4_K_M is the initial
installation candidate; no model is opened in development.

N0 success: reproducible CPU tests, strict data boundaries, no future-route
access in online policies, no acceptance invented from sequential traces,
capacity respected, failures preserved, working CLI and model guide. This is
not a performance threshold and does not establish scientific novelty.

## Research screening (not systematic/exhaustive)

Primary pages consulted on 2026-09-23:

- MoE-Infinity, 2401.14361v3 (2025-03-12), abstract screened:
  https://arxiv.org/abs/2401.14361 . Request-level sparsity-aware expert caching
  and prefetch already exist. No claim of inventing expert caching.
- DALI, 2602.03495v1 (2026-02-03), abstract and HTML inspected:
  https://arxiv.org/html/2602.03495v1 . Dynamic CPU/GPU assignment, residual-based
  prediction and workload-aware cache replacement are close predecessors.
- MoE-SpeQ, 2511.14102v1 (2025-11-18), abstract screened:
  https://arxiv.org/abs/2511.14102 . Speculative expert offloading and an
  amortization-roofline governor predate Tesy. Co-design alone is not novelty.
- AcceptMoE, 2608.02989v1 (2026-08-04), abstract screened:
  https://arxiv.org/abs/2608.02989 . Commitment-weighted/cache-conditioned expert
  eligibility explicitly changes the model distribution. Tesy's constraint is
  to retain natural target routing. That distinction does not prove novelty.
- SeqMoE, 2609.12978v1 (2026-09-11), HTML inspected, including sections 6–8:
  https://arxiv.org/html/2609.12978v1 . Multi-step prediction, deadline scheduling,
  forecast-based eviction and graph-compatible offloading are close prior art.
  No paper benchmark reproduced here.

Candidate question: does causal, target-routing-preserving residency across
bounded RAM and VRAM reduce exposed misses enough on the laptop to outweigh
wasted prefetch? Outcome UNKNOWN; novelty UNESTABLISHED. A three-tier hierarchy
alone is not a contribution. An oracle simulator is headroom analysis, not an
online policy, and a greedy next-use policy is not generally optimal with
variable sizes/costs.

## Design alternatives

KTransformers remains a comparison candidate; its relevant build/ISA/memory
requirements must be checked before running on the target. No unsupported
assumption that one tutorial's machine is its universal minimum.

Prefer an explicit CPU-only primitive now to unbuildable CUDA code. No host
measurements, source availability or external runtime builds are fabricated.
Remote Git creation returned 409 (empty repo); the connected commit action
requires a parent. Do not write main to hide the missing bootstrap boundary.
