# Routed-layer exactness protocol

Date: 2026-09-24

Branch:
`research/routed-layer-exactness-20260924`

Base commit:
`b4f8e6f6123313604d5dda321d01452faff3957d`

Base tree:
`eb35e7cf38a0a63ff706ecf7eaf76e6ce4b5096e`

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`

Evidence class:
prospective correctness-only routed-layer diagnostic.

## Prerequisite

The isolated physical gates established:

- `ASYNC_OVERLAP_MEASURED_GO`;
- `ASYNC_STEADY_TAIL_GO`.

Those results justify testing the mechanism against a real stock router event.
They do not establish routed-layer correctness or timing.

Correctness is the next gate. No routed-layer timing is authorized by this
protocol.

## Objective

For one stock gpt-oss-20b layer-0 decode event:

1. obtain the exact post-attention normalized activation that enters the MoE;
2. obtain the exact top-4 expert IDs produced by stock llama.cpp routing;
3. obtain the final routing weights actually multiplied into expert outputs;
4. obtain stock llama.cpp `ffn_moe_out-0`;
5. replay the same MoE event using Tesy's compact serial and async execution;
6. require numerical parity against the stock output before any timing work.

The stock router remains authoritative. Tesy does not recompute, predict,
replace, reorder, reduce or modify top-k routing.

## Frozen model and backend identity

Model:

`gpt-oss-20b-mxfp4.gguf`

Model SHA-256:

`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`

Model size:

`12109564352` bytes.

Backend:

`llama.cpp@4e416ee7308dd6b581796f1a6241276cd5982691`.

Capture run:

- stock llama.cpp graph;
- `n_gpu_layers=0`;
- context 4096;
- raw committed prompt;
- greedy sampling;
- exactly two generated tokens.

Frozen prompt:

`benchmarks/prompts/b0-b1-diagnostic.txt`

Prompt SHA-256:

`431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`

The capture uses the raw committed prompt rather than a chat template so OFF
and ON are compared against the exact same committed byte sequence.

## Stock callback OFF/ON exactness

Run the stock capture executable twice from fresh contexts:

### OFF

No `cb_eval` capture is enabled.

Persist exactly two greedy token IDs.

### ON

Install the passive routed-layer callback, but keep it disabled for prompt
prefill.

After the first greedy token is sampled, enable it only for the next
`llama_decode`. Capture layer 0 for that one-token decode event, then disable
it again.

Persist exactly two greedy token IDs.

Require:

`OFF token IDs == ON token IDs`.

A mismatch terminates the campaign. Callback data from a token-divergent run
must not be used for replay.

This is greedy token equality only. It is not bitwise tensor equality.

## Exact stock tensors

The pinned GPT-OSS graph calls `build_moe_ffn` immediately after
`attn_post_norm`.

The callback requests only these layer-0 tensors:

- `attn_post_norm-0`:
  exact F32 activation entering the stock router/MoE;
- `ffn_moe_topk-0`:
  exact I32 top-4 expert IDs;
- `ffn_moe_weights_softmax-0`:
  post-top-k softmax weights;
- `ffn_moe_weights_scaled-0`:
  scaled weights when the pinned graph emits that stage;
- `ffn_moe_out-0`:
  stock aggregated MoE output.

The replay uses `ffn_moe_weights_scaled-0` if that stage exists, otherwise
`ffn_moe_weights_softmax-0`.

It must never use the pre-softmax `ffn_moe_weights-0` tensor.

Capture requirements:

- activation: F32, 2880 values;
- selected experts: I32, exactly 4 unique IDs in 0..31;
- routing weights: F32, exactly 4 finite non-negative values;
- stock output: F32, 2880 values;
- decode input token equals generated token 0;
- decode output token equals generated token 1.

Capture activation/output binary files are each exactly 11,520 bytes and are
SHA-256 hashed by the runner.

## Replay math

The compact replay retains the pinned GPT-OSS expert math already validated by
the isolated diagnostic:

- real MXFP4 gate/up/down expert tensors from the GGUF;
- real F32 expert biases;
- `ggml_mul_mat_id`;
- gate/up bias add;
- `ggml_swiglu_oai(alpha=1.702, limit=7.0)`;
- down projection;
- down bias;
- multiply each expert output by its captured real routing weight;
- aggregate the four weighted outputs.

Synthetic `0.25` mixture weights are not used in routed-exactness mode.

## Controlled CPU/GPU partition

Replay two cases:

- h=2: top-k slots 0..1 GPU, slots 2..3 CPU;
- h=3: top-k slots 0..2 GPU, slot 3 CPU.

Classification:

`TOPK_SLOT_PREFIX_GPU_REMAINDER_CPU`.

This partition is deliberately controlled and deterministic. It is not a
cache policy, residency predictor or claim that those experts would be resident
under a production policy.

The exact stock expert IDs and weights are preserved within their original
top-k slot order.

## Serial and async comparators

For each h:

### Serial

- complete activation D2H;
- CPU subset compute;
- GPU subset compute;
- CPU partial H2D;
- GPU aggregation.

### Async

- complete activation D2H;
- enqueue GPU subset compute;
- execute CPU subset compute synchronously;
- synchronize GPU;
- CPU partial H2D;
- GPU aggregation.

Both use the same captured activation, selected experts, routing weights and
real model bytes.

## Numerical exactness gate

Reuse the already frozen isolated-operator numerical parity thresholds:

- relative max error <= 0.005;
- cosine similarity >= 0.9999;
- all values finite.

For both h=2 and h=3 require:

- `serial_vs_stock = PASS`;
- `async_vs_stock = PASS`;
- `async_vs_serial = PASS`.

The summary decision is:

`ROUTED_LAYER_EXACTNESS_GO`

only if all six comparisons pass and the OFF/ON token-ID gate passes.

Any mismatch terminates the campaign and routed-layer timing remains
unauthorized.

This is numerical parity for one routed FFN output. It is not bitwise equality
and not a full-model token-equivalence claim for a modified runtime.

## Build provenance

`scripts/bootstrap_routed_layer_exactness.sh` builds:

- `tesy-mixed-residency`;
- `tesy-routed-layer-capture`.

The atomic build manifest binds:

- clean Tesy HEAD;
- pinned llama.cpp HEAD;
- mixed replay source SHA-256;
- stock capture source SHA-256;
- native CMakeLists SHA-256;
- both executable SHA-256 values;
- resolved executable paths.

The physical runner recomputes every value before launch.

Required build configuration remains:

- Release;
- `GGML_CUDA=ON`;
- `GGML_BACKEND_DL=OFF`;
- CUDA architecture 89;
- GCC/G++ 15;
- pinned nvcc path.

## Live provenance

For stock OFF/ON capture:

- record exact argv;
- prove live `/proc/<pid>/exe`;
- prove exact `/proc/<pid>/cmdline`;
- hash the capture executable.

No CUDA mapping claim is required for the `--ngl 0` stock capture.

For h=2/h=3 replay:

- record exact argv;
- wait until the pinned build's `libggml-cuda.so` is mapped;
- temporarily SIGSTOP the correctness-only process;
- validate executable, exact argv and the unique mapped CUDA artifact;
- SIGCONT and finish the replay.

SIGSTOP/SIGCONT is provenance instrumentation only. No latency is measured in
this protocol.

## Resource gates

Monitor stock OFF, stock ON, h=2 and h=3 processes.

Require:

- at least one resource sample for every process;
- complete GPU telemetry;
- zero process swap;
- sampled GPU free headroom >= 1024 MiB;
- sampled host MemAvailable >= 2048 MiB;
- finite/valid telemetry.

Resource samples qualify campaign health only. They are not performance timing
or physical memory-traffic evidence.

## Output root and failure policy

Output root is no-replace.

Any failure creates/preserves:

`failure.json`

with classification:

`FAIL_CAMPAIGN_STAGE`.

Stop and preserve failure on:

- dirty Tesy or llama.cpp worktree;
- wrong model/prompt/backend identity;
- physical-host identity failure;
- competing GPU compute process;
- stale/wrong native build provenance;
- OFF/ON token mismatch;
- missing/wrong callback tensor;
- malformed top-k/weights;
- capture byte-size mismatch;
- executable/argv/CUDA provenance mismatch;
- non-finite values;
- serial-vs-stock parity failure;
- async-vs-stock parity failure;
- async-vs-serial parity failure;
- resource telemetry failure;
- process swap/headroom violation;
- OOM or unexpected process exit.

Debugging after a failure uses a new campaign identity.

## Explicit exclusions

This campaign does not measure:

- routed-layer latency;
- TTFT, TPOT or tok/s;
- full-model speedup;
- cache hit/miss behavior;
- prefetch;
- expert transfer traffic;
- physical PCIe/DRAM/NVMe traffic;
- bytes per committed token;
- run-to-run stability;
- speculation;
- novelty.

## Next discriminating gate

If `ROUTED_LAYER_EXACTNESS_GO`:

freeze a separate prospective routed-layer timing protocol using the exact same
stock capture/replay boundary, serial comparator and real router inputs. Its
median/tail thresholds must be registered before physical timing.

If exactness fails:

do not time the routed layer and do not advance to prefetch. Diagnose or kill
the integration boundary first.
