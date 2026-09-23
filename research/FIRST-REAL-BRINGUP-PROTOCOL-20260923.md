# First real bring-up: prospective diagnostic protocol

Date: 2026-09-23 UTC. Base: `a1aada5f24fb06d66b08566bf0d127ec3b78f994` on `research/novelty-runtime-foundation-20260923`. Campaign branch: `research/first-real-bringup-20260923`. The committed campaign HEAD is recorded by the runner.

## Objective and evidence boundary

Establish CUDA build, stock llama.cpp model load, passive trace OFF/ON generated-token-ID equality, native graph consistency, count-space LRU/Belady, and GGUF expert inventory on the physical reference laptop. These are diagnostic and trace-derived results, not speedup or measured expert-transfer claims. Preserve `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO` and `STATIC_NO_GO_B2_GPTOSS_EXPERT_LAZY`.

## Frozen inputs

- Model: `ggml-org/gpt-oss-20b-GGUF`, revision `a7443ebb00ba299cbbbf7e9b69487670447ae8c0`, file `/home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Tokenizer/template are embedded in this exact GGUF; no external template is used in this raw-prompt diagnostic.
- Backend: stock `ggml-org/llama.cpp` commit `4e416ee7308dd6b581796f1a6241276cd5982691`; Tesy tracer built against the same source. Stock source remains independent of the tracer.
- Toolchain: CUDA 13.3.73 from `/usr/local/cuda`, GCC/G++ 15.3.1 host compiler, CMake 4.3.0, Release, CUDA architecture 89, `TESY_BUILD_JOBS=4`. PATH includes the project venv and `/usr/local/cuda/bin`; `CC=/usr/bin/gcc-15`, `CXX=/usr/bin/g++-15`, `CUDAHOSTCXX=/usr/bin/g++-15`, `CUDACXX=/usr/local/cuda/bin/nvcc`.
- Stock smoke: runner default prompt, context 4096, 16 predicted, automatic GPU placement with 1024 MiB fit target, temperature 0, top-k 1, seed 42. Trace pair: runner default prompt, context 4096, 16 predicted, `TESY_TRACE_NGL=0`, raw prompt. The pair compares generated token IDs only. This CPU-only pair does not test GPU execution performance.
- Candidate: passive tracer ON; baseline: same tracer OFF for token equality. The separate stock CLI smoke checks model load and generation, not token parity against the tracer.
- Count-space capacities: 0, 16, 32, 64, 128, 256 slots. Byte-weighted simulation, if real trace and inventory pass: 16 GiB RAM cache, 4 GiB VRAM cache, `min_graph_seq=1`, byte LRU. The capacity is hypothetical and must be checked against observed shared-weight/KV/scratch envelope before any physical implementation claim.
- First output root: `results/bringup-20260923T203354Z`. Raw trace, prompts, logs and build products remain untracked. Versioned results contain summaries, hashes and provenance only. Every material retry gets a new root and prior failures remain.

## Stop gates

Stop a campaign on nonzero return, token mismatch, invalid graph sequence, missing provenance or telemetry, OOM, corruption, or resource violation. Debug with a fresh campaign identity after a committed correction. A build/toolchain failure is a diagnostic FAIL for that attempt. No threshold or model identity changes are allowed to turn a failure into PASS.

## Alternatives and decision

The installed CUDA compiler was absent from PATH. A direct CMake diagnostic with the default GCC 16 failed because CUDA 13.3 rejects host compilers newer than GCC 15. GCC/G++ 15 are already installed, so use them without changing the driver, kernel or system packages. Limit parallel build work to four jobs. vLLM remains B4 comparator; gpt-oss expert `--lazy-mode` remains the static B2 no-go. The next discriminating gate is actual trace/inventory-derived cache headroom.

## Pre-campaign checks

`bash -n` on changed scripts: PASS. CMake CUDA compiler-ID with GCC 16: diagnostic FAIL (unsupported GNU version). Fresh CMake configuration with GCC 15: PASS, CUDA 13.3.73, architecture 89. Real model gates: NOT_RUN until campaign starts.
