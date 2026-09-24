# n-cpu-moe fit-conflict handoff

Date: 2026-09-23  
Branch: `research/n-cpu-moe-fit-conflict-20260923`  
Base: `research/n-cpu-moe-pareto-sweep-20260923@5b005694ac408a9fc9697dd0c8350252aa665dc0`  
Implementation HEAD: use the current remote head of `research/n-cpu-moe-fit-conflict-20260923`; do not substitute an older conversational SHA.  
Draft PR: #9  
Reference model: locked gpt-oss-20b MXFP4 GGUF  
Pinned llama.cpp: `4e416ee7308dd6b581796f1a6241276cd5982691`

## Result

The direct `--fit on --n-cpu-moe N` sweep is
`STATIC_NO_GO_PIN_FIT_CONFLICT` for the pinned backend.

The preserved campaign
`results/n-cpu-moe-sweep-20260923T220215Z` is a real failed campaign, not a
capacity frontier. It completed `N=0` and failed while loading `N=4` after
the fitter refused user tensor buffer overrides and the real CUDA allocation
requested more memory than the device could provide.

Pinned-source inspection reproduces the mechanism. The exact campaign Tesy
HEAD `bb9ce3340c0214bee4a6d38ea645a9c30f0d8275` contains the incompatible
command composition.

The old runner now exits fail-closed.

## Replacement

The replacement is a two-stage stock placement experiment:

1. `--capacity-only`: cheap source-backed admission using pinned
   `llama-fit-params`;
2. capacity+timing: only after reviewing Stage 1, under a new campaign root.

The stock auto-fit baseline is first converted into explicit fitted
`-c/-ngl/-ts/-ot` arguments and later replayed with `--fit off`.

Manual points use explicit:

```text
--gpu-layers all --fit off --n-cpu-moe N
```

for `N = 0,4,8,12,16,20,24`.

Rejected capacity points are not deliberately loaded to produce an OOM.

## Evidence classes

- failed N=4 load: `MEASURED_FAILURE`;
- fit/override mechanism: `REPRODUCED_SOURCE_DIAGNOSIS`;
- `llama-fit-params --fit-print` rows: `SOURCE_BACKED_MEMORY_ESTIMATE`;
- capacity gate: `SOURCE_BACKED_CAPACITY_GATE`;
- replacement timing campaign: `NOT_RUN_REFERENCE_HOST`.

Estimator admission is not measured peak VRAM/RAM and does not prove a later
load will fit.

## Model-free implementation

Added:
- `src/tesy/placement_capacity.py` and strict parser/admission tests;
- `src/tesy/build_provenance.py` plus the locked reference toolchain/backend identity;
- `src/tesy/runtime_provenance.py` for live mapped-backend verification in timed runs;
- `scripts/run_n_cpu_moe_capacity_pareto.sh`;
- `scripts/publish_n_cpu_moe_capacity_result.sh` and model-free publication tests;
- `llama-fit-params` to the pinned llama.cpp bootstrap target.

Corrected:
- retired unsafe sweep runner;
- invalid B0/B1 interpretation;
- old Pareto protocol retirement status;
- implementation status.

Current PR checks are the authority for CI. Do not run the physical-host/model
gate until the current PR head is green.

The capacity-only gate also writes `build-provenance.json` and must PASS the
locked CMake/toolchain/server/`libggml-cuda.so` identity before estimator
work. A later timed campaign additionally writes `runtime-provenance.json`
for every fresh server process and verifies that the pre-hashed CUDA backend is
the library actually mapped by that process.

## First capacity-only attempt

`results/n-cpu-moe-capacity-20260923T232032Z` is preserved locally as
`FAIL_INSTRUMENTATION_PROBE_ROLE`.

It passed model verification and reference-host identity, then stopped before
build provenance or any capacity estimate because the runner applied the
`llama-cli` feature lock to `llama-server`. Source provenance itself was
PASS. The missing flags were CLI-only flags.

This is not a capacity result. The runner now uses `llama-cli` for the
backend feature/source probe and keeps `llama-server` under its own CLI and
exact build/hash provenance gates.

## Next operator gate

Do not run the full timing campaign yet.

On the physical reference laptop, after the current PR head is green:

```bash
cd ~/Projects/Tesy
git fetch
git switch research/n-cpu-moe-fit-conflict-20260923
git pull --ff-only

git status --short --branch
git rev-parse HEAD
git -C .deps/llama.cpp rev-parse HEAD
git -C .deps/llama.cpp status --porcelain

source .venv/bin/activate
python -m pip install -e '.[dev]'

ruff check .
pytest -q
bash -n scripts/*.sh

cmake --build .deps/llama.cpp/build --target help | grep -F llama-fit-params
cmake --build .deps/llama.cpp/build --parallel 4 --target llama-fit-params
.deps/llama.cpp/build/bin/llama-fit-params --version

campaign="results/n-cpu-moe-capacity-$(date -u +%Y%m%dT%H%M%SZ)"
echo "$campaign"

bash scripts/run_n_cpu_moe_capacity_pareto.sh --capacity-only \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"

cat "$campaign/tesy-head.txt"
cat "$campaign/llama-head.txt"
cat "$campaign/build-provenance.json"
cat "$campaign/admission-context.json"
cat "$campaign/auto-fit.json"
cat "$campaign/capacity-summary.json"
```

The output root is no-replace. Preserve any failure and do not retry with the
same campaign identity.


## Capacity-only publication to Git

After the capacity-only runner PASSes, publish the small campaign artifacts on a
new dedicated results branch. Do not commit the local `results/` root directly.

```bash
result_branch="research/n-cpu-moe-capacity-result-$(date -u +%Y%m%dT%H%M%SZ)"
git switch -c "$result_branch"

publish_dir="research/results/$(basename "$campaign")"

bash scripts/publish_n_cpu_moe_capacity_result.sh \
  "$campaign" \
  "$publish_dir"

cat "$publish_dir/RESULT.md"
cat "$publish_dir/publication-manifest.json"

git status --short
git add "$publish_dir"
git diff --cached --check
git diff --cached --stat
git commit -m "research: publish n-cpu-moe capacity gate"
git push -u origin "$result_branch"
```

The publication helper accepts only `capacity-only` campaigns, requires
`build-provenance.status == PASS`, rejects dirty campaign worktrees,
symlinks and unexpectedly large artifacts, and writes a hash manifest.

After push, send the terminal output plus the pushed branch name back for
analysis. Do not open or merge a timing campaign automatically.

## Decision after capacity-only

Inspect:
- `build-provenance.status == PASS` with the locked server/CUDA backend/toolchain;
- which `N` values are admitted;
- projected GPU and host headroom per point;
- the explicit stock auto-fit placement;
- any unexpected estimator stderr;
- campaign-start resource state.

Only then authorize a fresh full timing campaign. If fewer than two meaningful
manual points survive, kill the continuum experiment and pivot rather than
forcing a Pareto run.

No native Tesy cache, prefetch, speculation, >RAM execution or gpt-oss-120b run
is authorized by this handoff.
