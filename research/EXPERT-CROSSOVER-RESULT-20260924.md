# Expert crossover diagnostic result

Date: 2026-09-24  
Campaign: `results/expert-crossover-20260924T101753Z`  
Classification: `MEASURED_EXPERT_CROSSOVER_DIAGNOSTIC`

## Admission

The reference-laptop campaign completed with:

- focused validator PASS;
- CPU/GPU numerical parity PASS;
- zero process swap;
- complete GPU telemetry;
- peak sampled GPU usage 168 MiB;
- max GPU temperature 46 C;
- max GPU power 19.16 W;
- exact real expert encoded payloads from the locked GGUF.

The model lock establishes four active experts per token, so k=4 is the
model-active top-k shape. k=1 is the marginal per-expert diagnostic.

## CPU-buffer authority

The measured CPU buffer type was `CPU`.

This is the correct authority for comparison with Tesy's measured
`--n-cpu-moe` continuum. At the pinned llama.cpp source,
`llm_add_n_cpu_ffn_overrides` and `llm_ffn_exps_cpu_override` explicitly
assign expert tensors to `ggml_backend_cpu_buffer_type()`.

A CPU_REPACK path exists in ggml for MXFP4 on AVX2, but it is not the buffer
forced by `--n-cpu-moe`; it is therefore a separate future comparator, not a
replacement for this baseline.

## Measurements

### k=1

Requested encoded expert bytes: 13,253,760.

| component/path | median ms |
|---|---:|
| CPU compute | 0.340900 |
| GPU compute | 0.061410 |
| activation GPU -> Host | 0.008655 |
| output Host -> GPU | 0.006916 |
| weights Host -> GPU, default Host | 1.160258 |
| weights Host -> GPU, CUDA Host/pinned | 1.026884 |
| CPU_PATH | 0.356471 |
| COLD_GPU_NORMAL | 1.221667 |
| COLD_GPU_PINNED | 1.088294 |
| RESIDENT_GPU | 0.061410 |

### k=4

Requested encoded expert bytes: 53,015,040.

| component/path | median ms |
|---|---:|
| CPU compute | 1.142279 |
| GPU compute | 0.235275 |
| activation GPU -> Host | 0.008564 |
| output Host -> GPU | 0.006910 |
| weights Host -> GPU, default Host | 4.178803 |
| weights Host -> GPU, CUDA Host/pinned | 3.984424 |
| CPU_PATH | 1.157753 |
| COLD_GPU_NORMAL | 4.414078 |
| COLD_GPU_PINNED | 4.219700 |
| RESIDENT_GPU | 0.235275 |

The pinned requested-copy rate implied by these software-requested bytes and
completion wall times is about 12.9 GB/s for k=1 and 13.3 GB/s for k=4.
This is not physical PCIe traffic or a hardware-counter bandwidth claim.

## Crossover interpretation

A synchronous cold-GPU demand miss is much worse than CPU execution:

- k=1 pinned cold GPU / CPU path: about 3.05x slower;
- k=4 pinned cold GPU / CPU path: about 3.64x slower.

A resident GPU hit is much better than CPU execution:

- k=1 CPU path / resident GPU: about 5.80x;
- k=4 CPU path / resident GPU: about 4.92x.

For an idealized serial cache that executes hits resident on GPU and handles
misses by synchronously copying weights then running GPU, the hit probability
needed merely to match always-CPU execution is:

`p_break_even = (cold_gpu - cpu_path) / (cold_gpu - resident_gpu)`

Using the pinned-copy medians:

- k=1: about 71.3%;
- k=4: about 76.8%.

Using the default Host-copy medians:

- k=1: about 74.6%;
- k=4: about 77.9%.

These are diagnostic break-even calculations, not measured full-model speedups.
They assume serial paths and omit cache lookup/scheduling overhead.

## Architecture decision

`NO_GO_BLOCKING_DEMAND_TRANSFER`.

Do not build a cache whose miss policy is:

`miss -> synchronously copy expert to GPU -> execute GPU`.

The real-shape transfer cost is already several times the CPU-resident expert
path.

The surviving architecture is narrower:

`GPU-resident hit -> GPU expert compute`

`GPU miss -> CPU expert compute`

and any Host->GPU weight transfer should be **prefetch**, completed before the
expert is demanded. Exact routing remains authoritative; prefetch may only
change residency.

This architecture is justified only if measured routing locality provides
enough useful resident hits and wasted prefetch can be bounded.

## Next discriminating gate

Rerun the existing byte-weighted native routing simulation using the newly
admitted native expert inventory. Do not relabel the old exploratory
simulation.

The immediate comparison is the simulated VRAM hit rate versus the crossover
break-even and, more importantly, the potential hit fraction for a
GPU-hit/CPU-miss policy.

No new model/GPU campaign is required for this gate.

## Claim boundary

The crossover uses real encoded weights and pinned ggml CPU/CUDA expert
operators. Copy bytes are requested tensor bytes, not physical PCIe traffic.
Derived path medians are sums of separately measured components and are not an
overlapped pipeline measurement. No full-model Tesy speedup, production cache,
prefetch benefit, >RAM execution or novelty claim follows.
