# N2 bring-up protocol — reference laptop

Date: 2026-09-23
Status: prospective DEVELOPMENT protocol
Model-bearing execution: NOT_RUN in the GitHub-only development session

## Purpose

Bring up a pinned stock backend and the first locked MoE model without yet claiming a Tesy optimization.

The first result is a trustworthy baseline and routing-observability boundary, not a performance win.

## Frozen software baseline

Tesy backend lock:
`configs/backends.lock.json`

Current stock llama.cpp pin:
`4e416ee7308dd6b581796f1a6241276cd5982691`

The pin may only change prospectively with a lock update and fresh build/provenance.

## Host preflight

From the Tesy branch on the physical laptop:

```bash
git status --short --branch
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
ruff check .
pytest -q
tesy doctor
```

Record the JSON from `tesy doctor`.

Do not infer the physical host state from historical MOSAIC measurements.

## Build stock backend

```bash
bash scripts/bootstrap_llama_cpp.sh
```

Then prove binary/source provenance:

```bash
tesy backend probe \
  --binary .deps/llama.cpp/build/bin/llama-cli \
  --source-dir .deps/llama.cpp
```

A backend-probe PASS is not a model PASS.

## Model

Install only the first model described in `MODELOS_A_INSTALAR.md`:

`gpt-oss-20b-mxfp4-gguf`

Verify it:

```bash
tesy models verify gpt-oss-20b-mxfp4-gguf \
  ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
```

Then run the capacity plan:

```bash
tesy plan --model gpt-oss-20b-mxfp4-gguf \
  --path ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
```

## Stock smoke

Before timing, run a short deterministic/non-conversation smoke using the stock binary and the model's own template/metadata.

Exact command arguments must be copied from the pinned binary's help on the host and committed to a campaign manifest before a measured comparison. Do not copy a command from a different llama.cpp revision.

Required evidence:
- model path/size/SHA;
- binary path/SHA;
- source commit and clean status;
- actual GPU/device listing;
- context and generation count;
- exit code;
- output token IDs or output hash;
- peak RAM/VRAM/swap;
- stdout/stderr paths.

## Baseline order

Once smoke is correct:

1. B0 stock automatic placement;
2. B1 `--cpu-moe`;
3. bounded `--n-cpu-moe` calibration;
4. B2 `--lazy-mode` only if the selected model/path supports the required behavior;
5. native trace instrumentation;
6. only after trace evidence, any Tesy-specific cache/residency candidate.

## Important source finding

At the pinned llama.cpp commit, `ggml_backend_sched_compute_splits()` already recognizes host-resident weights consumed by `GGML_OP_MUL_MAT_ID`, reads `node->src[2]` as the expert ID tensor, builds a used-expert bitset and copies only selected experts.

The GPT-OSS model implementation uses the common `build_moe_ffn` path, and that path constructs expert products through `build_lora_mm_id -> ggml_mul_mat_id`.

Therefore the first Tesy route-trace hook should be architecture-generic at the common `MUL_MAT_ID`/scheduler boundary rather than a Qwen-specific router reimplementation.

This is source analysis, not a reproduced runtime result.

## Stop conditions

Stop the campaign on:
- source/binary provenance mismatch;
- model hash mismatch;
- unexpected model download or second artefact;
- OOM or swap storm;
- non-zero exit;
- corrupted/non-finite output;
- missing required resource telemetry;
- instrumentation that changes routing/output before a separate diagnostic identity is created.
