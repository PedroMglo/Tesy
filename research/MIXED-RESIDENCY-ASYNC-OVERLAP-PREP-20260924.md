# Mixed-residency async-overlap preparation

Date: 2026-09-24

Branch: `research/mixed-residency-async-overlap-20260924`

Development base commit:
`fafa8b9883c818c367c4c32f69b82cf9a82fc049`

Development base tree:
`c26e2256d78f6d6f13f981f21c4c1fb0e129a118`

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`

Evidence class:
`PROSPECTIVE_IMPLEMENTATION / SOURCE_AUDITED / MODEL_FREE_PARTIAL_VALIDATION / PHYSICAL_NOT_RUN`

## Objective

Prepare the smallest actual CPU/GPU concurrency experiment justified by the
published post-D2H overlap-bound result, without executing a new physical
campaign and without adding prefetch, cache policy, speculation or routing
changes.

The admitted prerequisite is
`research/MIXED-RESIDENCY-OVERLAP-BOUND-RESULT-20260924.md`.

That campaign measured a weighted serial isolated diagnostic of
0.5167518333 ms and derived a post-D2H overlap bound of 0.4039387111 ms.
The prospectively frozen 10% gate was 0.46507665 ms and the persisted
decision was `OVERLAP_IMPLEMENTATION_GO`.

That decision authorizes an experiment with concurrency. It does not establish
a measured async speedup.

## Stack state and separation of concerns

Official GitHub Stack #22 remains rooted at `main` with the previously
confirmed open-PR order:

`#9 -> #11 -> #10 -> #12 -> #13 -> #14 -> #15 -> #16 -> #17 -> #19 -> #21`.

PR #9 now targets `main` but remains `CONFLICTING`. The existing
`research/GITHUB-STACK-22-HANDOFF-20260924.md` records the 50/70 commit
divergence and real merge conflicts.

This async-overlap work is deliberately separate:

- no `gh stack rebase`;
- no `gh stack push`;
- no force-push;
- no automatic merge;
- no manual base edits;
- no conflict resolution for #9;
- no PR was opened manually for this new branch.

The stack blocker does not alter the experiment protocol, threshold or
baseline.

## Backend source audit

Pinned source was inspected before implementing concurrency.

In `ggml/src/ggml-backend.cpp`:

- `ggml_backend_graph_compute()` calls
  `ggml_backend_graph_compute_async()` and then synchronizes the backend;
- `ggml_backend_graph_compute_async()` delegates directly to the backend
  graph implementation without the wrapper's unconditional synchronize.

In the pinned CPU backend:

- graph compute calls `ggml_graph_compute()` synchronously;
- the backend synchronize callback is null.

In the pinned CUDA backend:

- graph compute launches work on the CUDA stream and returns;
- backend synchronize calls `cudaStreamSynchronize()`.

Therefore the minimum mechanism matching the admitted bound does not require a
worker thread:

1. complete activation GPU->CPU copy;
2. enqueue GPU subset compute asynchronously;
3. execute CPU subset compute synchronously on the caller thread;
4. synchronize the GPU;
5. copy CPU partial output to GPU;
6. run GPU aggregation.

If a CUDA kernel path internally synchronizes, the measured candidate will
include that loss of concurrency rather than hiding it.

The candidate additionally requires the selected GPU device to report
`caps.async=true`.

## Implementation

`native/tesy_mixed_residency.cpp` now has an opt-in
`--async-overlap` mode.

The existing serial execution remains a distinct lambda and does not call
`ggml_backend_graph_compute_async`.

Only h=1,2,3 execute the async candidate. h=0 and h=4 remain serial anchors.

Before timing, both paths are independently checked against the same all-CPU
top-4 reference. The async path uses the same frozen numerical thresholds as
Stage B and the bound campaign.

For mixed cases, serial and async samples are collected in the same process.
Sample order alternates deterministically:

- even sample index: serial then async;
- odd sample index: async then serial.

Each invocation is complete and synchronized before the next invocation.

No `std::thread` was added.

## Raw and derived contracts

Async raw schema:

`tesy.mixed_residency_async_raw.v1`

Raw evidence includes:

- same serial `direct_wall` timing;
- `async_wall` for h=1..3;
- independent `async_parity` for h=1..3;
- null async fields for h=0/h=4;
- GPU and CPU advertised async capability;
- CPU weight/bias buffer names;
- unchanged component diagnostics.

Validator:

`src/tesy/mixed_residency_async_overlap.py`

Validated summary schema:

`tesy.mixed_residency_async_summary.v1`

Trace-weighted result schema:

`tesy.mixed_residency_async_weighted.v1`

The same admitted histogram is required, including classification and SHA-256
identity in the physical runner.

## Prospectively frozen decision

No result from the future async campaign has been observed.

The decision threshold is frozen before execution and reuses the previous
engineering gate:

`weighted_async <= 0.90 * weighted_serial`.

Both weighted arms use same-campaign measured medians.

For h=1..3, the candidate term is the measured async median.
For h=0/h=4, the candidate term equals the measured serial anchor.

Decision labels:

- `ASYNC_OVERLAP_MEASURED_GO`;
- `ASYNC_OVERLAP_COMPLEXITY_NO_GO`.

No threshold will be changed after the campaign is executed.

## Python environment correction

The predecessor overlap-bound campaign preserved a failed root where system
Python could not import `tesy`.

The new runner does not use bare `python3 -m tesy ...`.

It requires exactly the project interpreter:

`$TESY_ROOT/.venv/bin/python`

and writes `python-provenance.json`, including:

- resolved interpreter path;
- Python version;
- imported `tesy` module path;
- PASS only if the imported module resolves under the current Tesy worktree.

Inline Python snippets that use only the standard library may still use system
`python3`; all Tesy module execution uses the project virtual environment.

## Physical runner

New runner:

`scripts/run_mixed_residency_async_overlap.sh`

The runner preserves the admitted overlap-bound provenance/resource gates and
adds:

- project-.venv identity;
- `--async-overlap` in exact argv provenance;
- async schema validation;
- trace-weighted serial-vs-async decision;
- failure publication for both ERR-trapped and explicit nonzero exits.

It refuses an existing output root. Failed campaign roots must remain
preserved and are never reused.

## Static/source validation performed

**REPRODUZIDO / PASS** from the current remote branch bytes:

- Python files touched by the new gate have no lines longer than 100 columns;
- serial execution block contains no
  `ggml_backend_graph_compute_async`;
- no `std::thread` exists in the native source;
- async source order is GPU enqueue -> CPU compute -> GPU synchronize;
- GPU async capability is gated;
- runner requires `.venv/bin/python`;
- runner has no-replace output-root behavior;
- runner passes `--async-overlap`;
- runner invokes the async validator and weighting module;
- runner contains the exact admitted histogram SHA-256;
- runner preserves FAIL classification and resource/swap gates.

## Synthetic validation performed

A model-free reconstructed sandbox using the exact remote Python module and
test bytes was used for the new validator.

Initial test execution found one **test-fixture failure**: the synthetic timing
fixture generated a zero timing sample for a 0.02 ms component. The production
validator correctly rejected that non-positive sample. No production threshold
or validator rule was weakened.

The fixture was corrected to use strictly positive perturbations.

After correction:

- focused async validator tests: **7 PASS**;
- Python `compileall` on the exact new module/test bytes: **PASS**.

This is model-free validation of the Python contract only. It is not a
repository-checkout test, native compile, CUDA test or physical measurement.

## Tests not run in this environment

The current execution environment does not expose the user's
`/home/pmglo/Projects/Tesy` checkout and cannot materialize the private repo
as a complete filesystem checkout.

Therefore:

- `bash -n scripts/run_mixed_residency_async_overlap.sh`: **NOT_RUN_LOCAL_CHECKOUT_REQUIRED**;
- Ruff on the touched repo files: **NOT_RUN_LOCAL_CHECKOUT_REQUIRED**;
- contract pytest modules requiring repository files:
  **NOT_RUN_LOCAL_CHECKOUT_REQUIRED**;
- native CUDA compile of `tesy-mixed-residency`:
  **NOT_RUN_REFERENCE_HOST**;
- physical async-overlap campaign: **NOT_RUN_REFERENCE_HOST**;
- full repository pytest suite: **NOT_RUN_NOT_REQUIRED_FOR_DEVELOPMENT_GATE**.

GitHub CI was not triggered merely to consume Actions minutes. The current CI
also does not compile the changed CUDA mixed-residency target.

## Stop conditions

The prospective campaign stops and preserves FAIL on:

- dirty required worktree;
- wrong Tesy or llama.cpp provenance;
- missing/wrong model or histogram identity;
- wrong project Python environment;
- competing GPU compute process;
- missing CUDA build identity;
- GPU async capability absent;
- serial parity mismatch;
- async parity mismatch;
- non-finite or malformed timing;
- missing runtime provenance;
- incomplete GPU telemetry;
- process swap;
- RAM/VRAM headroom violation;
- OOM, backend error, corruption or unexpected process exit.

Debugging after any such failure uses a new campaign identity.

## Claim boundary

The next campaign, if it passes, will measure actual overlap only for the
isolated real-weight mixed FFN operator.

It will not by itself establish:

- full-model throughput or latency improvement;
- physical PCIe, DRAM or NVMe traffic;
- cache benefit;
- prefetch benefit;
- bytes per exact committed token;
- run-to-run stability;
- a scientific novelty claim.

Prediction and prefetch remain out of scope.

## Next gate

Before any physical execution on the laptop:

1. check out the exact async-overlap branch;
2. require a clean worktree and pinned llama.cpp checkout;
3. run focused shell/Python/contract tests;
4. compile the pinned CUDA target;
5. record the exact final candidate HEAD/tree and binary identity;
6. only then launch a new no-replace campaign root.

No physical async-overlap campaign was executed while preparing this branch.
