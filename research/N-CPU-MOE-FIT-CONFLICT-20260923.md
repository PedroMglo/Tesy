# n-cpu-moe / --fit conflict diagnosis

Date: 2026-09-23  
Pinned llama.cpp: `4e416ee7308dd6b581796f1a6241276cd5982691`  
Failed campaign: `results/n-cpu-moe-sweep-20260923T220215Z`  
Classification: `REPRODUCED_SOURCE_DIAGNOSIS_WITH_MEASURED_FAILURE`

## Result

The original `--n-cpu-moe` Pareto sweep is retired for this pin.

The failure is not evidence that `n-cpu-moe=4` is intrinsically infeasible.
It is evidence that the frozen command combined two stock mechanisms that are
not composable in this llama.cpp revision:

- `--n-cpu-moe N` installs tensor buffer overrides before model init;
- `--fit on` can only rewrite placement when user tensor buffer overrides are
  not already present.

When the fit path needs to change placement, it therefore aborts its adjustment.
The server then continues with the user placement and can fail later during the
real CUDA allocation.

## Measured failure

The preserved campaign completed the first `n-cpu-moe=0` observation and
stopped fail-closed at `n-cpu-moe=4`.

The failing server log contains, in order:

```text
common_fit_params: failed to fit params to free device memory:
model_params::tensor_buft_overrides already set by user, abort
...
allocating 9331.49 MiB on device 0: cudaMalloc failed: out of memory
...
llama_server: exiting due to model loading error
```

No Pareto, speedup, capacity or placement conclusion follows from this failed
campaign.

## Source reproduction at the exact pin

At the pinned source:

1. `--n-cpu-moe N` calls `llm_add_n_cpu_ffn_overrides(...)` and writes those
   rules into `params.tensor_buft_overrides`.
2. `common_params_fit_impl` checks whether
   `mparams->tensor_buft_overrides` is already populated before its placement
   rewrite and throws:
   `model_params::tensor_buft_overrides already set by user, abort`.
3. The fitter can return before that guard when the initial placement already
   satisfies the target. This is why a configuration such as `--cpu-moe` can
   appear to coexist with `--fit` when it already fits; that does not make the
   two mechanisms generally composable.
4. For MoE models, stock auto-fit itself may generate tensor buffer overrides
   while searching the placement. Therefore stock auto-fit is not equivalent to
   a clean manual `n-cpu-moe=0` endpoint.

## Decision

Do not retry `scripts/run_n_cpu_moe_sweep.sh` on this pin. The runner now exits
with `STATIC_NO_GO_N_CPU_MOE_FIT_CONFLICT`.

The replacement is
`scripts/run_n_cpu_moe_capacity_pareto.sh`, which separates three concerns:

1. use pinned `llama-fit-params` once to obtain the explicit stock auto-fit
   placement for the frozen context and headroom;
2. use `llama-fit-params --fit-print` with `--fit off --n-cpu-moe N` as a
   source-backed capacity admission estimator for manual points, without
   deliberately loading rejected points;
3. benchmark only admitted placements, with `--fit off`, fresh processes and
   exact token-trajectory equality.

The auto-fit baseline is benchmarked from its emitted explicit arguments
(`-c`, `-ngl`, optional `-ts` and `-ot`) rather than invoking the fitter
inside timed runs.

## Evidence boundary

`llama-fit-params --fit-print` reports projected model/context/compute memory.
That is an estimator result, not measured peak VRAM/RAM and not physical
PCIe/NVMe traffic.

Admission cannot prove a subsequent load will fit. Timed runs still enforce
measured resource stop conditions and preserve any failure under a new campaign
identity.

No Tesy-native cache, prefetch, custom expert kernel, >RAM or novelty claim is
authorized by this diagnosis.
