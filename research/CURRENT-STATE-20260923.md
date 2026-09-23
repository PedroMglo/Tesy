# Tesy current state — 2026-09-23

Status: DEVELOPMENT foundation; first model-bearing campaign not yet executed.

## Repository line

- repository: `PedroMglo/Tesy`;
- base branch: `main`;
- development branch: `research/novelty-runtime-foundation-20260923`;
- draft PR: #3;
- `main` contains only the bootstrap root commit plus any later explicitly merged work; this branch must not be auto-merged.

Always rediscover the live HEAD before execution.

## Scientific state

Broad architecture novelty is NO-GO based on the current prior-art screen.
Tesy is not allowed to claim expert caching, MoE offload, CPU/GPU scheduling,
speculative expert prefetch, expert-union-aware speculation or a generic
NVMe/RAM/VRAM hierarchy as inventions.

The useful question is empirical:

> On the reference 8 GiB VRAM / 32 GiB RAM laptop, which existing or narrowly
> modified exact MoE execution boundary actually minimizes expensive expert
> movement while preserving usable conversational latency?

A narrower contribution may be proposed only after a concrete measured gap.

## Software boundary already built

Model-free/source work includes:
- backend/model locks;
- physical-host identity checking;
- fail-closed model verification;
- capacity planning;
- native passive router tracing;
- paired trace token equality;
- LRU and Belady count-space headroom;
- GGUF encoded expert-payload inventory;
- byte-weighted trace replay;
- stock bring-up/provenance runners.

The native tracer is diagnostic-only because callback readback can alter
synchronization. Stock backend runs remain the timing baseline.

## Model-bearing blocker

The first admitted model is the locked gpt-oss-20b MXFP4 GGUF described in
`MODELOS_A_INSTALAR.md`.

The model has not been downloaded or opened by this GitHub-only development
session. The physical RTX 4060 Laptop/CUDA build and runtime state have also not
been observed here.

Therefore there is currently:
- no real routing trace;
- no cache hit-rate result;
- no expert byte inventory from the actual GGUF;
- no physical I/O/H2D measurement;
- no Tesy speedup;
- no >RAM result.

## First physical-host campaign

After the user installs the one locked model, use a clean checkout/venv and run:

```bash
bash scripts/run_reference_bringup.sh \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  results/bringup-<new-campaign-id>
```

The output root must not exist.

If this passes diagnostically, next derive count-space and byte-weighted
headroom from the retained trace/inventory before selecting any custom cache.

## Decision after first trace

- Belady/LRU both poor at affordable capacity: do not build a fancy cache.
- Belady good, LRU poor: policy/prediction headroom exists.
- simple LRU already good: prefer simplicity until latency proves otherwise.
- byte-weighted headroom small: test CPU-resident execution/crossover instead
  of forcing GPU expert caching.

Only after those observations should Tesy create a branch for a native runtime
candidate.
