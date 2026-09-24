# n-cpu-moe manual continuum shape diagnostic

Date: 2026-09-24
Branch: `research/n-cpu-moe-continuum-shape-20260924`
Base commit/tree: `c55b3e88d9d3a148fc825f12e12ac6d82e290003` / `ffaa885e9c8b0ed4d5fb553154e25354e932039d`
Evidence class: prospective diagnostic protocol; model execution NOT_RUN at authoring

## Objective and decision

The published single-observation pilot measured a large performance and peak
VRAM difference between `N=12` and `N=24`. It did not measure `N=16` or
`N=20`. Run one new campaign in this exact order:

1. `N=12` anchor;
2. `N=16`;
3. `N=20`;
4. `N=24` anchor.

One fresh `llama-server` process and one 64-token request are required per
point. The anchors are remeasured within the same campaign. Prior pilot
measurements are context only, never substitutes for these observations.

Alternatives considered: repeat auto-fit/N12 now; measure N16/N20 against the
previous pilot; start a balanced confirmatory sweep. The chosen four-point
diagnostic buys within-campaign curve shape at lower cost. It is not a
confirmatory campaign or Pareto claim.

## Frozen authority and workload

The source capacity publication remains commit
`5a8bbf08eb95069b1847f724e5d1be98c6392678`, which admitted all four
manual points. The new campaign rechecks admission under its measured start
state and immediately before every load. Manual server and fit-print argv use
`--ctx-size 4096 --gpu-layers all --n-cpu-moe N --fit off`.

Use the same locked gpt-oss-20b MXFP4 GGUF, pinned llama.cpp source/build,
B0/B1 diagnostic prompt, 4096 context, parallel 1, CPU threads/batch threads
12/12, 64 generated tokens, temperature 0, top-k 1, seed 42, disabled prompt
reuse and disabled warmup as the successful timing pilot. No model download is
part of this gate.

The runner requires clean Tesy and backend worktrees, locked model verification,
reference-host doctor PASS, no competing GPU compute process, pinned backend
feature/build provenance, exact live `/proc/<pid>/cmdline` equality with each
frozen `server-argv.json`, mapped CUDA backend identity, and source capacity
evidence ancestry. The campaign records exact commit and binary hashes.

## Unchanged admission and stop gates

- Fit-print estimated device total + 1024 MiB GPU target + 16 MiB rounding
  guard must fit current free GPU memory.
- Fit-print estimated host total + 2048 MiB host guard + 16 MiB rounding
  guard must fit current MemAvailable.
- Before the request, runtime CUDA0 model-buffer MiB must be within 2 MiB
  of same-placement fit-print logical CUDA0 MiB; projected Host allocation
  above zero requires a positive `CPU_Mapped` buffer. The Host mmap span is
  classified `NOT_COMPARABLE_MMAP_SPAN`.
- Every request must generate exactly 64 token IDs with
  `timings.predicted_n == 64`. All four token-ID SHA-256 values must match.
  This is greedy token equality, not bitwise or numerical parity.
- GPU telemetry must be complete and finite, process swap zero, sampled free
  GPU memory at least 1024 MiB, and sampled MemAvailable at least 2048 MiB.
  Resource monitor exit must succeed. Record TTFT, prompt/decode throughput,
  request wall, peak GPU use, RSS, swap, temperature and power.

Any mismatch, OOM, missing provenance or telemetry, non-finite value, resource
violation or command failure ends the campaign. Preserve its root and use a
new campaign identity for debugging or rerun. No threshold is to be revised
after observing a point.

## Execution and publication boundary

After the implementation is committed and the worktree is clean, use:

```bash
campaign="results/n-cpu-moe-continuum-shape-$(date -u +%Y%m%dT%H%M%SZ)"
bash scripts/run_n_cpu_moe_capacity_pareto.sh --continuum-shape \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

The output root is no-replace. Successful execution produces
`continuum-summary.json` with class
`MEASURED_STOCK_PLACEMENT_CONTINUUM_SHAPE_DIAGNOSTIC` and prints
`PASS_DIAGNOSTIC_STOCK_PLACEMENT_CONTINUUM_SHAPE`. The summary must retain
`next_gate = MANUAL_REVIEW_REQUIRED`. Raw local campaign data, including any
prompt-bearing artifacts, stays out of Git. A separately reviewed publication
may copy only selected aggregate evidence with checksums.

This gate can indicate a candidate knee or motivate confirmatory repeats. A
single observation per point cannot establish a stable ranking, Pareto
frontier, physical traffic, Tesy speedup or novelty. After inspecting its
curve, choose between confirmatory repeats and the CPU-vs-transfer-vs-GPU
expert crossover. The crossover remains NOT_RUN.

## Implementation verification record

Base: `c55b3e88d9d3a148fc825f12e12ac6d82e290003`.
Tests: `bash -n` PASS; all 17 embedded Python blocks compile; `ruff` PASS;
`git diff --check` PASS; 125 model-free pytest tests PASS with third-party
plugin autoload disabled because the installed rerun plugin attempts a socket
for its status DB under the sandbox.
Reference-host/model execution: NOT_RUN at authoring.
Failures: none recorded for this new campaign mode at authoring.
Limitation: implementation tests cannot establish real-model timing or
hardware admission.
