# n-cpu-moe timing pilot handoff

Date: 2026-09-24  
Branch: `research/n-cpu-moe-timing-pilot-20260924`  
Base evidence commit: `5dd06218584bc5f0e72b05102eb6ff483a9dbfe7`  
Capacity campaign: `research/results/n-cpu-moe-capacity-20260923T233416Z/`

## State

The historical capacity campaign projected `N=12,16,20,24` as admitted and
`N=0,4,8` as rejected, but its publication has since been downgraded to
`INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN`. Those sets remain historical
estimator output only and are not current admissions.

The stock auto-fit placement is not equivalent to a single manual `N`; its
frozen explicit argv uses `-ngl 25` plus tensor overrides that move block-12
FFN tensors and a suffix of later expert tensors to CPU.

A full multi-point timing sweep is not authorized. The three-point timing
pilot is also now **NOT_AUTHORIZED_PENDING_PHYSICAL_CAPACITY_REVALIDATION**.
The runner rejects the corrected historical publication before timing.

## Selected pilot

Run only the three-point diagnostic pilot:

1. `auto-fit-frozen`;
2. `n-cpu-moe-12`;
3. `n-cpu-moe-24`.

The runner mode is:

```text
scripts/run_n_cpu_moe_capacity_pareto.sh --timing-pilot
```

It rechecks current-host capacity for all three placements before starting any
server, then performs one fresh-process observation per placement.

## Required local validation

Before freezing a new implementation HEAD, validate the changed script,
Python modules and focused tests. Run the full local suite once at the end if
the focused gate passes. No model run is part of this protocol revision.

For this revision:

```bash
bash -n scripts/run_n_cpu_moe_capacity_pareto.sh
ruff check src/tesy/runtime_provenance.py src/tesy/placement_telemetry.py \
  src/tesy/publish_timing_pilot.py tests/test_runtime_provenance.py \
  tests/test_placement_telemetry.py tests/test_publish_timing_pilot.py \
  tests/test_capacity_runner_contract.py
python -m compileall -q src/tesy/runtime_provenance.py \
  src/tesy/placement_telemetry.py src/tesy/publish_timing_pilot.py \
  tests/test_runtime_provenance.py tests/test_placement_telemetry.py \
  tests/test_publish_timing_pilot.py tests/test_capacity_runner_contract.py
pytest -q tests/test_runtime_provenance.py tests/test_placement_telemetry.py \
  tests/test_publish_timing_pilot.py tests/test_capacity_runner_contract.py \
  tests/test_placement_capacity.py
```

Run `pytest -q` once after the focused gate, if it remains cheap. Before a
future physical run, repeat the local gate on the exact clean HEAD.

No full GitHub Actions run is required for this development gate. The repository
workflow is configured so the full matrix runs only at `Ready for review` or
manual dispatch.

## Pilot stop rules

Preserve and stop on:

- source/build/model/host provenance mismatch;
- current-host capacity rejection for any of the three placements;
- model/server load failure or OOM;
- runtime backend mapping mismatch;
- exact live server argv mismatch;
- CUDA0 model buffer differing from the same-placement fit-print projection
  by more than 2 MiB;
- missing positive `CPU_Mapped` buffer when Host logical allocation is
  projected, or any Host mmap span treated as equal to Host logical bytes;
- missing placement evidence;
- process swap;
- measured GPU/host headroom violation;
- missing valid GPU telemetry;
- generated-token trajectory mismatch.

Never reuse a failed output root.

## Publication

Only a completed pilot with
`PASS_DIAGNOSTIC_STOCK_PLACEMENT_TIMING_PILOT` may be published.

Use:

```bash
python -m tesy.publish_timing_pilot "$campaign" "$publish_dir"
```

The publisher copies only derived summaries/provenance/identity artifacts.
Raw request streams, server logs, resource samples and placement files remain
local; the publication manifest records their byte sizes and SHA-256 identities.

The result publication must use a new dedicated branch based on the exact pilot
implementation branch.

## Decision after pilot

Do not fill in `N=16` or `N=20` automatically.

First inspect:

- exact trajectory equality;
- live capacity recheck;
- realized CUDA0 parity, Host mmap presence and the explicit
  `NOT_COMPARABLE_MMAP_SPAN` classification;
- TTFT/prompt/decode timing;
- observed VRAM/RSS/swap;
- thermal/resource state.

Only then choose whether to:

- kill the manual continuum;
- repeat a suspicious point;
- freeze a small confirmatory set;
- proceed to the CPU-vs-transfer-vs-GPU crossover gate.

No Tesy-native cache, prefetch, speculation, >RAM execution or gpt-oss-120b
run is authorized by this pilot alone.

## Local gate repair, 2026-09-24

- Objective: unblock the model-free gate before any model-bearing pilot run.
- Base commit/tree: `b0b88e830a902b6f95fc50b1d118b4ff3d03db95`;
  clean worktree at the start of this repair.
- Evidence class: reproduced local test failure and verified model-free checks.
  The source contract test searched for a continuous warning phrase, while
  the runner split that phrase across adjacent Python string literals.
- Alternatives: loosen the source-text test, or keep its explicit warning
  contract and make the phrase continuous in the runner source.
- Decision: make the phrase continuous in the runner source. The generated
  `claim_boundary` text is unchanged; no placement, threshold, workload or
  measurement logic changed.
- Tests: `ruff check .`, `python -m compileall -q src tests`, `pytest -q`
  (104 passed), `bash -n scripts/*.sh`, four lock/config JSON parse checks,
  and the three placement/publisher CLI help checks all passed. The editable
  development install also completed.
- Failures: the initial gate had one failed source contract test out of 104.
  No campaign root was created by this repair.
- Limitations: model-bearing pilot and physical timing remain NOT_RUN. The
  prior handoff's exact Tesy HEAD pin must be updated to the repair commit
  before a new campaign starts.
- Next discriminating gate: execute the frozen three-placement pilot with a
  clean worktree and the updated exact Tesy HEAD pin.

## First physical pilot attempt, 2026-09-24

- Objective: run the frozen three-placement diagnostic timing pilot.
- Base commit/tree: `3421a1876a212f952c555ce03c167fc59f91cfa6`;
  clean Tesy and pinned llama.cpp worktrees at campaign start.
- Campaign root (local, preserved):
  `results/n-cpu-moe-timing-pilot-20260924T000834Z`.
- Evidence class: measured physical-host startup and failure; source-backed
  diagnosis of the missing logging level. The reference host and model gates,
  build provenance, all three capacity projections, and the fresh pre-run
  admission for `auto-fit-frozen` passed. The server loaded the model and
  `/health` returned OK. Its stderr had no `model buffer size` or offloaded
  layer rows, so the placement check failed before the first request.
- Failure: `failure.json` records `FAIL_CAMPAIGN_COMMAND` at runner line 694,
  `PlacementTelemetryError: server log contains no model buffer sizes`. No
  timing summary or publication was produced. `N=12` and `N=24` remain
  NOT_RUN; no performance conclusion follows.
- Alternatives: infer placement from the fit projection alone, or make the
  pinned server expose observed allocation rows before requesting tokens.
- Decision for future campaigns: add `--verbosity 4` to timing-pilot server
  commands. In pinned llama.cpp, backend INFO rows are mapped to verbosity 4;
  the server default is 3. Keep the 2 MiB observed-placement check. This
  change is prospective and does not reclassify the failed campaign.
- Tests/limits: the failed run itself verifies that default logging lacks the
  required rows. A contract test and model-free gate check the new command;
  physical emission and placement parity remain NOT_RUN for the revised
  command. The failed campaign root must never be reused.
- Next discriminating gate: start a new campaign identity from a clean,
  exactly pinned implementation and confirm observed model buffers before
  the first token request.

## Second physical pilot attempt, 2026-09-24

- Objective: run the same frozen three-placement diagnostic with placement
  logging enabled. Base commit/tree: `eab64f546ea8635efd2538f14bee2e265485cb40`;
  clean Tesy and pinned llama.cpp worktrees at campaign start.
- Campaign root (local, preserved):
  `results/n-cpu-moe-timing-pilot-20260924T001215Z`.
- Evidence class: measured physical-host placement log and source-backed
  interpretation. The model loaded, `/health` passed, and the three fit
  projections plus fresh auto-fit admission passed. Before any request, the
  observed CUDA0 model buffer was 6095.35 MiB versus 6095 MiB projected;
  the observed CPU_Mapped buffer was 10949.33 MiB versus 5440 MiB projected.
- Failure: the pre-request 2 MiB Host placement gate returned status `FAIL`
  with a +5509.33 MiB difference. `failure.json` records exit code 2 at
  runner line 698. No tokens, timing summary, or publication were produced;
  `N=12` and `N=24` remain NOT_RUN.
- Interpretation, not a measured physical-RAM claim: pinned llama.cpp creates
  mmap-backed host buffers from the first to last tensor offset in a context
  (`get_mapping_range`), whereas the no-allocation fit path sums allocated
  tensor sizes. The two reported Host quantities can therefore differ when
  the mapped interval spans gaps. The log's buffer size does not by itself
  establish resident DRAM bytes or expert traffic.
- Alternatives: remove mmap with `--load-mode none` in a new protocol, or
  design a placement proof that compares like-for-like tensor allocation
  while recording mmap span and residency separately. Neither was applied
  after this observation.
- Decision: preserve this negative result and stop the current pilot. Do not
  raise the 2 MiB tolerance, relabel this run PASS, or publish a timing result.
- Tests/limits: the current model-free gate passed (105 tests, lint and shell
  syntax). Physical placement parity and all timing observations remain
  NOT_RUN under a revised protocol. This failed root must never be reused.
- Next discriminating gate: prospectively specify a comparable Host placement
  measure and its physical-residency interpretation, then validate it in a
  new diagnostic campaign before any timing campaign.

## Prospective argv-bound CUDA placement protocol

- Objective: replace the invalid Host equality gate before another physical
  attempt. Base commit `3039bbd34e8f1f7a504f61eba9281309a2f06369`, tree
  `dd57d4532ffde99ae7261862e8d4973dc7db3e13`;
  clean local worktree after advancing to the verified PR #10 remote HEAD.
- Evidence class: source-backed semantics and model-free validation. Attempt 2
  physically measured CUDA0 parity (6095.35 versus 6095 MiB), while its
  10949.33 MiB `CPU_Mapped` span and 5440 MiB logical Host fit value are
  different quantities. Neither failed campaign is reclassified.
- Alternatives: change runtime load mode, increase Host tolerance, or retain
  stock mmap behavior and bind the exact live argv while checking only
  comparable CUDA0 bytes plus Host mmap buffer presence.
- Decision: retain the frozen stock placement, model and workload. Require
  `server-argv.json` to equal `/proc/<pid>/cmdline`, pinned executable/source/
  build and mapped pre-hashed `libggml-cuda.so`, CUDA0 parity within 2 MiB,
  and a positive `CPU_Mapped` buffer when Host logical allocation is nonzero.
  Classify Host mmap span as `NOT_COMPARABLE_MMAP_SPAN`; measure RSS, swap and
  MemAvailable separately. The publisher rejects contradictory telemetry
  PASS fields and non-finite JSON. No per-tensor or physical byte claim follows.
- Tests: `bash -n` on the changed runner, focused `ruff check` and
  `compileall`, and focused `pytest` (52 passed) completed. After publisher
  hardening, its targeted tests passed (12 passed). One final full local
  `pytest -q` passed (124 passed). `git diff --check` passed. The initial
  focused lint found one pre-existing overlong contract-test line; formatting
  was corrected before the PASS gates.
- NOT_RUN: the revised protocol has not been exercised on the physical host;
  64-token greedy trajectory equality and timings remain NOT_RUN.
- Failures and limits: both pre-request failures remain preserved at their
  original roots. The revised gate cannot establish individual expert
  placement, resident DRAM, physical traffic or a stable performance winner.
- Next discriminating gate: audit the implementation and publication diff,
  freeze a clean exact HEAD, then create a new campaign identity for only
  `auto-fit-frozen`, `N=12` and `N=24`. Never reuse either failed root.
