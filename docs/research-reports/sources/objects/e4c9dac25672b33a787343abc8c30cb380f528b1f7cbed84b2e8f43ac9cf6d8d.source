# capacity-only attempt 20260923T232032Z

Date: 2026-09-23  
Local output root: `results/n-cpu-moe-capacity-20260923T232032Z`  
Classification: `FAIL_INSTRUMENTATION_PROBE_ROLE`

## Observed stop

The campaign stopped before `build-provenance.json`, auto-fit or any manual
capacity estimate was produced.

Artifacts established before the stop:

- locked gpt-oss-20b model verification: `PASS`;
- reference-host check: `PASS`;
- GPU snapshot: `OK`;
- no competing GPU compute process at the doctor snapshot;
- llama.cpp source HEAD: exact pinned commit and clean checkout.

The generated `backend.json` had source provenance `PASS` but overall
`status = FAIL`.

The only reported missing feature flags were:

```text
--no-display-prompt
--prompt
--simple-io
--single-turn
```

These are `llama-cli` surface requirements from the backend lock, not
`llama-server` requirements.

## Diagnosis

The capacity runner invoked:

```text
tesy backend probe --binary llama-server
```

while `configs/backends.lock.json` defines a feature surface that was
originally validated with `llama-cli`.

This mixed two distinct provenance roles:

- `llama-cli`: source/backend feature-surface probe;
- `llama-server`: execution binary, separately validated by its required
  server flags and by exact build provenance.

Therefore this failure is an instrumentation/provenance-boundary defect. It is
not a model, hardware, placement, capacity or performance result.

## Correction

The runner now probes backend features/source identity with `llama-cli`.

It still:

- validates the exact measured `llama-server` SHA-256;
- validates the exact measured `libggml-cuda.so` SHA-256;
- validates the frozen CMake/compiler/CUDA toolchain;
- checks the required `llama-server` CLI flags separately;
- checks the required `llama-fit-params` flags separately.

The local failed output root remains preserved and must not be reused.

Retry requires a new campaign identity after current-head model-free CI PASS.
