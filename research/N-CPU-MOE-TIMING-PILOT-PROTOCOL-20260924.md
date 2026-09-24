# n-cpu-moe minimal timing pilot protocol

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Capacity evidence commit: `5dd06218584bc5f0e72b05102eb6ff483a9dbfe7`  
Capacity evidence: `research/results/n-cpu-moe-capacity-20260923T233416Z/`  
Classification: prospective diagnostic pilot

This revision applies only to a future campaign identity. The preserved
pre-request failures at `results/n-cpu-moe-timing-pilot-20260924T000834Z` and
`results/n-cpu-moe-timing-pilot-20260924T001215Z` remain FAIL; neither
produced a timing observation.

## Purpose

The historical capacity campaign originally projected manual placements
`N=12,16,20,24` as admitted and `N=0,4,8` as rejected. Review later
established that its snapshot did not prove the required physical host. The
publication is now `INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN`; those projected
sets are preserved as descriptive source output and are **not** current
capacity admissions.

The stock auto-fit placement is not equivalent to one simple
`--n-cpu-moe N`: the published fitter output keeps `-ngl 25` and emits
explicit tensor overrides.

Before spending a balanced multi-point timing campaign, measure exactly three
fresh-process placements:

1. `auto-fit-frozen`;
2. `n-cpu-moe-12`;
3. `n-cpu-moe-24`.

`N=16` and `N=20` are NOT_RUN in this pilot.

## Discriminating questions

`auto-fit-frozen` versus `N=12` tests whether the stock fitter's
tensor/suffix-aware placement behaves materially differently from a coarse
prefix-based CPU-MoE boundary at the first capacity-admitted manual point.

`N=12` versus `N=24` brackets the admitted manual continuum and tests the
broad trade between more GPU-resident expert compute and the all-experts-CPU
endpoint.

If these three points do not expose a useful diagnostic trade, measuring
`N=16/N=20` is not automatically justified.

## Placement authority

The historical stock auto-fit placement remains frozen as evidence, but it is
not sufficient to authorize a new timing pilot while the publication is
inconclusive.

Before any future timing pilot, the runner requires the published capacity
manifest to prove:

- classification `SOURCE_BACKED_CAPACITY_GATE`;
- `performance_gate=PASS`;
- `physical_host_status=PHYSICAL`;
- the publication admitted set exactly matches the raw capacity summary.

The current corrected historical publication fails this gate by design.

The runner also verifies that capacity evidence commit
`5dd06218584bc5f0e72b05102eb6ff483a9dbfe7` exists in the pilot ancestry.
A future physical-host revalidation must use a new campaign identity and a
prospectively updated evidence pin before timing can be authorized.

The runner freezes the full server argv in `server-argv.json`, launches that
argv directly, and requires byte-for-byte argument-list equality with the live
`/proc/<pid>/cmdline` before any request. Pinned source, build and mapped
backend identity must also PASS. This is aggregate placement authority under
the frozen stock backend, not per-tensor equality.

Manual placements use:

- `--ctx-size 4096`;
- `--gpu-layers all`;
- `--n-cpu-moe 12` or `24`;
- `--fit off`.

The target remains authoritative. No routing, top-k, quantization, context,
sampling, token confirmation or expert semantics are changed.

## Frozen workload

- locked gpt-oss-20b MXFP4 GGUF;
- pinned llama.cpp commit;
- committed B0/B1 diagnostic prompt;
- context: 4096;
- parallel: 1;
- CPU threads / batch threads: 12 / 12;
- exactly 64 generated tokens;
- temperature: 0;
- top-k: 1;
- seed: 42;
- prompt reuse disabled on the request (`cache_prompt=false`);
- server warmup disabled;
- fresh `llama-server` process per placement.

There is exactly one observation per placement. This is not confirmatory
performance evidence.

## Provenance gates

Before model timing:

- locked model verification PASS;
- reference-host identity PASS;
- no competing GPU compute process;
- clean Tesy and llama.cpp worktrees;
- pinned source/feature probe through `llama-cli`;
- locked CMake/compiler/CUDA/server/`libggml-cuda.so` provenance PASS;
- published capacity evidence identity PASS;
- prompt/backend/model hashes recorded.

After each server health PASS and before its request:

- verify `/proc/<pid>/exe`;
- require exact `/proc/<pid>/cmdline` equality with `server-argv.json`;
- verify the pre-hashed `libggml-cuda.so` is the backend actually mapped by
  that process;
- compare the `llama-server`-reported CUDA0 model buffer with the
  same-placement `llama-fit-params --fit-print` logical CUDA0 projection,
  requiring a delta no greater than 2 MiB;
- when fit-print projects Host model allocation above zero, require a positive
  `CPU_Mapped` Host model buffer in the runtime load log;
- record the Host mmap buffer span as `NOT_COMPARABLE_MMAP_SPAN`, with no
  equality test against fit-print Host logical tensor allocation.

Process RSS, swap and system MemAvailable are measured separately. The mmap
span is neither resident DRAM nor physical traffic; CUDA0 aggregate parity
does not prove per-tensor identity.

## Capacity admission

Two admission layers are required.

First, at campaign start, pinned `llama-fit-params --fit-print on` estimates
all three exact placements under the measured campaign-start GPU/RAM state.

Second, immediately before every individual load, the runner:

- measures free GPU memory;
- measures MemAvailable/SwapFree;
- records GPU temperature/pstate;
- rejects competing GPU compute processes;
- re-evaluates the same placement estimate against those fresh resources.

Admission requires:

- estimated device total + 1024 MiB GPU target + 16 MiB rounding guard <=
  current free GPU memory;
- estimated host total + 2048 MiB host guard + 16 MiB rounding guard <=
  current MemAvailable.

This is `SOURCE_BACKED_MEMORY_ESTIMATE`, not measured peak VRAM/RAM and not
proof that the subsequent load will fit.

## Realized placement gate

The quantitative equality gate is limited to CUDA0: the same-placement
fit-print logical CUDA0 model MiB and runtime CUDA0 model-buffer MiB must
differ by at most 2 MiB. The estimator prints integer MiB; the server logs
fractional MiB. This tolerance is unchanged from the failed campaigns.

For projected Host model allocation above zero, the pinned mmap runtime must
report a positive `CPU_Mapped` model buffer. Its reported span is retained but
classified `NOT_COMPARABLE_MMAP_SPAN`. The fit path uses `no_alloc=true` and
`load_mode=NONE`, so fit-print Host bytes describe logical tensor allocation.
The mmap runtime buffer spans first-to-last mapped tensor offsets and may
include gaps. The former Host equality gate was invalidated by Attempt 2 and
is removed prospectively, without changing either failed campaign.

`tesy.stock_placement_telemetry.v2` is a
`MEASURED_RUNTIME_PLACEMENT_LOG_DIAGNOSTIC`. Combined with frozen/live argv
equality and pinned executable/source/build/mapped backend, it qualifies
aggregate CUDA0 placement and Host mmap buffer presence. It does not prove
per-tensor equality or physical VRAM/DRAM/PCIe traffic.

## Exactness gate

The first successful run establishes the deterministic trajectory.

Every later placement must have:

- exactly 64 generated token IDs;
- `timings.predicted_n == 64`;
- the exact same token-ID SHA-256.

Mismatch stops and preserves the campaign.

This is greedy token equality only, not bitwise tensor equality, numerical
parity or sampling-distribution equivalence.

## Runtime resource gates

Sampled telemetry records:

- whole-GPU used memory;
- GPU temperature;
- GPU power;
- process RSS;
- process swap;
- MemAvailable;
- SwapFree.

Every run must have:

- valid GPU telemetry sufficient to establish peak use;
- process VmSwap == 0;
- observed free GPU memory at peak >= 1024 MiB;
- observed MemAvailable >= 2048 MiB;
- quantitative CUDA0 model-buffer parity PASS within 2 MiB and positive
  `CPU_Mapped` Host buffer presence when Host logical allocation is projected;
- Host mmap span classified `NOT_COMPARABLE_MMAP_SPAN`;
- non-empty placement/load log extract retained as raw diagnostic evidence;
- exact live argv and runtime backend provenance PASS;
- finite, complete telemetry and successful resource-monitor exit.

OOM, missing telemetry, resource violation, token mismatch or provenance
failure stops the campaign and requires a new identity.

## Timing scope

Recorded fields include:

- server-ready wall time;
- client-observed TTFT;
- request wall time;
- prompt tokens/s;
- decode tokens/s;
- observed peak GPU memory;
- RSS/swap;
- thermal/power samples.

The aggregate classification is
`MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC`.

One sample per placement is intentionally insufficient for a stable ranking or
Pareto claim. The pilot can only decide whether a larger experiment is worth
buying.

The summary must set:

`next_gate = MANUAL_REVIEW_REQUIRED`.

## Operator entrypoint

**Current status: NOT_AUTHORIZED_PENDING_PHYSICAL_CAPACITY_REVALIDATION.**

Do not execute the timing-pilot command with the current historical capacity
publication. The runner is intentionally fail-closed and will reject it.

After a new capacity-only campaign passes current physical-host verification,
freeze a new publication/evidence commit prospectively before authorizing a
fresh timing campaign identity.

The historical command shape remains:

```bash
campaign="results/n-cpu-moe-timing-pilot-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_n_cpu_moe_capacity_pareto.sh \
  --timing-pilot \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

The output root is no-replace. Never reuse a failed campaign identity.

A successful pilot ends with:

`PASS_DIAGNOSTIC_STOCK_PLACEMENT_TIMING_PILOT`.

## Publication boundary

Only a successful pilot may be published.

Use:

```bash
python -m tesy.publish_timing_pilot "$campaign" "$publish_dir"
```

The publisher stages only derived summaries, provenance and identities.

Raw request streams, server logs, resource samples, pre-run snapshots and
placement files remain outside Git. Their byte sizes and SHA-256 identities are
recorded in the publication manifest.

## Decision after pilot

Do not fill in `N=16` or `N=20` automatically.

Review:

- exact trajectory equality;
- campaign-start and per-run capacity admission;
- realized placement evidence;
- TTFT/prompt/decode timing;
- observed VRAM/RSS/swap;
- pre-run headroom and thermal/resource state.

Then choose whether to kill the manual continuum, repeat a suspicious point,
freeze a small confirmatory set, or proceed to the
CPU-vs-transfer-vs-GPU crossover gate.

## Claim boundary

No Tesy speedup, physical PCIe/NVMe/DRAM byte, >RAM execution or novelty claim
follows from this pilot.
