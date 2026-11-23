# ADR-0002 — baseline matrix before custom expert caching

Date: 2026-09-23
Status: ACCEPTED

## Context

Second-pass prior-art review found that recent llama.cpp and external research already implement several mechanisms Tesy initially considered building.

A custom cache before reproducing them would be poor engineering and weak science.

## Frozen exploratory baseline order

### B0 — stock automatic placement

Use the pinned stock llama.cpp build with its normal placement policy.

Purpose: establish the actual reference host/model behavior.

### B1 — stock CPU-MoE

Use `--cpu-moe`, then bounded `--n-cpu-moe` sweeps selected during a separate calibration phase.

Purpose: measure the value of keeping expert weights in host RAM while hot/shared work remains on GPU.

### B2 — stock lazy/on-demand capability

Probe the exact pinned commit for `--lazy-mode` support and whether it applies to the selected model/expert tensors.

Purpose: determine whether upstream already provides enough >RAM behavior for the next experiment.

Do not assume a CLI option means expert-granular physical NVMe reads.

### B3 — external research baseline

Where architecture and host assumptions match, reproduce the MIT `CAN230921/moe-expert-cache` trace/demand-mmap mechanism on a fresh branch/campaign.

Purpose: avoid reimplementing a public mechanism and establish a stronger oversubscription baseline.

Its Qwen3-specific trace patches do not automatically support gpt-oss.

### C0 — Tesy candidate

Only implement a native Tesy residency mechanism after B0-B3 identify a concrete gap.

The candidate must state which exact physical behavior differs from the best baseline.

## Comparison rules

Same:
- model bytes and hash;
- tokenizer/chat template;
- context;
- prompt/output target;
- sampling/seed;
- CPU affinity/threads where applicable;
- host resource envelope;
- fresh-process/warm-state policy;
- instrumentation class.

Report separately:
- load/TTFT;
- prompt throughput;
- decode throughput/TPOT;
- RAM/VRAM/swap;
- requested source bytes;
- measured storage bytes if actually observable;
- H2D expert bytes if actually observable;
- routing/cache counters.

Do not compare a lower-quality quantization against a higher-quality baseline and call it a scheduler speedup.
