# Manual stock placement continuum shape diagnostic

> **Publication correction — 2026-09-24**
>
> Current classification:
> `INCONCLUSIVE_INVALID_CAPACITY_AUTHORITY_AND_INCOMPLETE_EXECUTION_PROVENANCE`.
> The raw/aggregate observations below remain preserved, but this campaign is
> not an admitted reference-host continuum gate. Its frozen capacity authority
> was later withdrawn, and the recorded Tesy execution commit is not retained
> in current repository history. Revalidation requires a new campaign identity
> after a fresh PHYSICAL-host-verified capacity publication.

Date: 2026-09-24. Campaign: `n-cpu-moe-continuum-shape-20260924T083136Z`.
Branch: `research/n-cpu-moe-continuum-shape-20260924`.
Execution base commit/tree: `89771fa4ba3a017978f5931c94779110a7f8d22f` / `cb7cc651c95a746ca8ce5aa54429ff14e6407f30`.
Historical execution class: `MEASURED_STOCK_PLACEMENT_CONTINUUM_SHAPE_DIAGNOSTIC`; execution-host physical/virtual status is **not proven by the committed publication evidence**.

## Objective and decision

Measure one fresh-process observation at each of N=12, 16, 20 and 24 under the
prospective [protocol](../../N-CPU-MOE-CONTINUUM-SHAPE-PROTOCOL-20260924.md).
The earlier N=12/N=24 timing pilot is context, not a substitute for either
anchor in this campaign. Alternatives considered before execution were another
auto-fit/N12 comparison, two middle points compared only against the old
pilot, or a larger confirmatory sweep. The four-point within-campaign shape
diagnostic was selected and committed before measurement.

The historical runner printed
`PASS_DIAGNOSTIC_STOCK_PLACEMENT_CONTINUUM_SHAPE`, but that execution-level
output is **not publication-admitted** under the current evidence contract.
The result remains preserved as a single-observation historical diagnostic.
No stable winner, Pareto frontier, or current capacity decision is established.

## Frozen identity and gates

- Model: locked gpt-oss-20b MXFP4 GGUF, 12,109,564,352 bytes, SHA-256
  `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.
- Backend: pinned llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`;
  server SHA-256 `facdeefaff9d54818f7786f8812125231f28281ae496b62946fbb7e7127fe456`.
  Build provenance and mapped CUDA backend checks passed.
- Workload: B0/B1 diagnostic prompt SHA-256
  `431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`,
  context 4096, one 64-token greedy request per fresh process, temperature 0,
  top-k 1, seed 42, threads 12/12, parallel 1, no warmup and no prompt reuse.
- Reference-host identity, model verification, current-host capacity admission,
  live argv, placement telemetry and runtime binary provenance passed.
  Tesy and backend worktrees were clean at campaign start.
- The four generated 64-token ID sequences had the same SHA-256:
  `c64fefef84af574bdd51ff71625016d434f958497a58748c5de78ca280ce6b42`.
  This tests greedy token equality, not bitwise or numerical parity.
- Every observation had zero process swap, zero failed GPU samples, at least
  1024 MiB sampled free VRAM and 2048 MiB sampled available RAM. All required
  request and resource metrics were finite. `CPU_Mapped` is retained as
  `NOT_COMPARABLE_MMAP_SPAN`, not resident DRAM or logical Host allocation.

## Measured single observations

| N CPU MoE layers | TTFT ms | Prompt tok/s | Decode tok/s | Request wall ms | Peak VRAM MiB | Peak RSS GiB | Swap MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | 712.60 | 218.32 | 43.444 | 2162.96 | 6548 | 11.78 | 0 |
| 16 | 752.90 | 205.96 | 38.881 | 2373.51 | 4932 | 11.78 | 0 |
| 20 | 866.64 | 178.73 | 34.551 | 2690.36 | 3312 | 11.78 | 0 |
| 24 | 991.96 | 155.95 | 31.491 | 2992.87 | 1696 | 11.78 | 0 |

The peak VRAM values are sampled device-wide `nvidia-smi --query-gpu=memory.used` usage, rounded to MiB; they are not process-attributed VRAM.
The summary JSON retains unrounded measurements, pre-run resources, GPU
temperature/power, projected and observed model-buffer values and checks.

## Derived interpretation and limits

From N=12 to N=24 in this campaign, sampled peak VRAM fell by 4852 MiB
(4.74 GiB), while decode throughput fell by 27.51%, TTFT rose by 39.20%,
and request wall time rose by 38.37%. Intermediate observations show a
monotonic trade-off. No sharp knee is evident in these four points; that is
an inference from one run per point, not a confirmed curve.

The earlier pilot's N=12 and N=24 decode rates were about 11% higher than
their newly measured anchors. Cross-campaign drift is therefore material;
neither campaign alone supports a stable ranking. The transient `nvidia-smi`
failure observed during preflight occurred before campaign start; the repeat
succeeded and all campaign GPU samples passed. No campaign failure or
threshold change was recorded.

No physical NVMe/PCIe/DRAM expert traffic, Tesy speedup, >RAM execution,
stochastic distribution parity or novelty follows. One 64-token request per
placement cannot qualify sustained throughput or tail latency.

## Publication and next gate

The ignored `results/` campaign root retains raw requests, server logs and
resource samples locally. This directory publishes only selected aggregate
evidence and identities. `publication-manifest.json` records SHA-256 and size
for every raw artifact and checksum for each selected published artifact.
Raw prompt-bearing request streams are not committed.

Required revalidation gate: publish a new capacity-only campaign with explicit
`virtualization=PHYSICAL`, retained execution provenance and a new campaign
identity; only then may a new continuum run be considered for admission.
Historical values in this directory must not be promoted as current evidence.

Model-free verification of the runner before this campaign: 125 pytest tests,
`ruff`, `bash -n`, all 17 embedded Python blocks, and `git diff --check`
passed. A confirmatory timing run was `NOT_RUN`.
