# CPU-vs-transfer-vs-GPU expert crossover protocol

Date: 2026-09-24  
Branch: `research/expert-crossover-20260924`  
Classification: prospective microbenchmark; physical execution NOT_RUN at authoring

## Question

For the admitted gpt-oss-20b expert shape on the reference laptop, compare the
serial cost of three residency choices without implementing a Tesy cache:

1. CPU-resident expert execution;
2. copying cold expert weights from Host memory into a preallocated GPU slot,
   then executing the expert on GPU;
3. executing an already-resident expert on GPU.

This is the cheapest mechanism-level gate after the measured placement
continuum. It asks whether moving weights can plausibly beat moving activations
to CPU at the real expert shape.

## Admitted expert contract

The native GGUF inventory passed on the physical reference laptop:

- 24 MoE layers;
- 32 experts per layer;
- encoded payload: 13,253,760 bytes per expert;
- matrix tensors: MXFP4, shape `[2880, 2880, 32]`;
- bias tensors: F32, shape `[2880, 32]`.

Pinned llama.cpp gpt-oss graph construction uses three expert projections
(gate/up/down), expert-indexed biases and `SwiGLU_OAI`.

The microbenchmark verifies the same shape/type/byte contract directly against
the GGUF before measuring. It also requires the final GGUF expert dimension to
have a byte stride equal to one exact expert slice; otherwise the run fails.

## Mature execution boundary

Do not implement MXFP4 kernels or Transformer logic.

Use pinned ggml public operators:

- `ggml_mul_mat_id`;
- `ggml_add_id`;
- `ggml_swiglu_oai(alpha=1.702, limit=7.0)`;
- expert weighting and sum.

CPU and CUDA therefore execute the same semantic expert FFN graph through
their mature ggml backends.

The router itself is excluded. Expert IDs are deterministic compact
`0..k-1`; this is not a routing-distribution benchmark.

## k values

Measure:

- `k=1`: marginal single-expert crossover;
- `k=4`: the model's active top-k shape and batching behavior.

For k=1, requested expert-weight bytes are exactly 13,253,760.

For k=4, requested expert-weight bytes are exactly 53,015,040.

Each input and aggregated output activation is 2880 F32 values = 11,520 bytes.

## CPU buffer authority

This experiment is tied to the measured `--n-cpu-moe` continuum.

At the pinned source, `llm_add_n_cpu_ffn_overrides` and
`llm_ffn_exps_cpu_override` explicitly force expert tensors to
`ggml_backend_cpu_buffer_type()`. Therefore the admitted crossover requires
the CPU weight buffer type to be exactly `CPU`.

The generic loader can expose optimized CPU extra/repack buffers and MXFP4 has
an AVX2 repack path, but that is a separate comparator. It must not silently
replace the `--n-cpu-moe` CPU baseline.

The selected CPU buffer type and allocated bytes are recorded.

## Measured components

All timings are completion wall times with explicit backend synchronization.

### CPU-resident path

Measure separately:

- GPU -> Host input activation copy;
- CPU expert FFN compute;
- Host -> GPU aggregated output activation copy.

Derived serial diagnostic:

`CPU_PATH = D2H_ACTIVATION + CPU_COMPUTE + H2D_OUTPUT`

### Cold GPU path

Weights are copied into an already allocated GPU tensor set.

Measure:

- default Host-buffer -> GPU requested weight copy;
- when available, CUDA Host-buffer/pinned -> GPU requested weight copy;
- GPU expert FFN compute.

Derived serial diagnostics:

`COLD_GPU_PAGEABLE = H2D_WEIGHTS_PAGEABLE + GPU_COMPUTE`

`COLD_GPU_PINNED = H2D_WEIGHTS_PINNED + GPU_COMPUTE`

The pinned variant is conditional on the CUDA backend exposing a Host buffer
type.

### Resident GPU path

`RESIDENT_GPU = GPU_COMPUTE`

## Important timing boundary

The derived paths are sums of separately measured medians. They are
**serial diagnostic bounds**, not measurements of an overlapped pipeline.

Setup excluded from timed components:

- GGUF file reads;
- tensor allocation;
- CPU repack/population;
- GPU slot allocation;
- graph construction;
- backend initialization/JIT warmup.

If later architecture uses overlap/prefetch, that must be measured separately.

## Copy-byte semantics

`requested_weight_bytes`, `activation_input_bytes`, and
`activation_output_bytes` are tensor bytes requested through ggml copy APIs.

They are **not physical PCIe traffic**.

No PCIe, DRAM or NVMe physical-byte claim is permitted without an appropriate
hardware/driver instrument.

The wall time is named requested-copy completion wall time: the code issues the
ggml copy and synchronizes the relevant backend before the measurement ends.

## Numerical gate

Before timing, CPU and GPU execute the same expert graph and output 2880 F32
values.

All outputs must be finite.

Prospectively frozen diagnostic parity:

- max-absolute error normalized by `max(1, max_abs_cpu)` <= 0.005;
- cosine similarity >= 0.9999.

Failure stops the campaign. These thresholds establish this microbenchmark's
CPU/GPU numerical comparability only; they are not bitwise equality.

## Samples

Reference settings:

- CPU threads: 12;
- warmup iterations: 3;
- samples: 21;
- compute inner repetitions/sample: 5;
- weight-transfer inner repetitions/sample: 4;
- activation-transfer inner repetitions/sample: 100.

Record every sample plus median, p95, min, max and mean.

The first campaign is diagnostic. It does not establish a universal crossover
threshold or tail-latency claim.

## Build/provenance

Build in a dedicated directory with:

- pinned llama.cpp source;
- Release;
- GCC/G++ 15;
- CUDA compiler from `/usr/local/cuda/bin/nvcc`;
- CUDA architecture 89;
- `GGML_CUDA=ON`;
- `GGML_BACKEND_DL=OFF`.

Compilation is a separate operator step and must finish before the timed
campaign.

The campaign records:

- clean Tesy HEAD;
- clean pinned llama.cpp HEAD;
- model verification;
- reference-host doctor;
- no competing GPU compute process;
- CMake identity;
- microbenchmark SHA-256;
- selected `libggml-cuda.so` SHA-256;
- live process executable;
- exact argv;
- exact mapped build `libggml-cuda.so`.

## Resource stop rules

Stop/preserve FAIL on:

- model/source/host/build provenance mismatch;
- competing GPU compute process;
- missing or unexpected live CUDA backend;
- numerical parity failure;
- non-finite measurement;
- incomplete GPU telemetry;
- process swap;
- sampled free GPU memory below 1024 MiB;
- sampled MemAvailable below 2048 MiB;
- command/output corruption.

Never reuse a failed output root.

## Operator flow

Build first:

```bash
bash scripts/bootstrap_expert_crossover.sh
```

Then, from a clean worktree, create a fresh campaign:

```bash
campaign="results/expert-crossover-$(date -u +%Y%m%dT%H%M%SZ)"

bash scripts/run_expert_crossover.sh \
  /home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf \
  "$campaign"
```

Successful execution prints `PASS_EXPERT_CROSSOVER`.

## Decision after measurement

Compare k=1 and k=4 independently.

The first decision is architectural:

- if serial cold-GPU transfer+compute is already slower than the CPU-resident
  path by a wide margin, a naive demand-transfer expert cache is weak;
- if cold-GPU is faster or close enough that realistic overlap could change
  the result, a residency/prefetch mechanism remains worth investigating;
- resident-GPU compute quantifies the maximum useful headroom after a cache hit.

Do not implement a cache or prefetcher merely because resident GPU is faster.
The miss path and routing locality must jointly justify it.

## Claim boundary

This experiment measures one real expert FFN shape through pinned ggml CPU/CUDA
operators and requested-copy completion wall times. It does not measure full
model throughput, physical PCIe/DRAM/NVMe traffic, a production cache,
overlapped prefetch, >RAM execution, Tesy speedup or novelty.
