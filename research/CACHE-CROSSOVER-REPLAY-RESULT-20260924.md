# Cache crossover locality replay result

Date: 2026-09-24  
Campaign: `results/cache-crossover-replay-20260924T103638Z`  
Classification: `INCONCLUSIVE_REPLAY_PROVENANCE_NOT_PRESERVED`

## Evidentiary correction

Review found that the referenced replay campaign root is not preserved in the
reviewed tree. The publication therefore lacks the exact execution commit/tree,
clean-worktree proof, command, raw derived output and hash manifest needed to
audit the simulator invocation that produced the reported values.

The numerical replay values below are retained as historical context only.
They are **not admitted** as a current cache gate, and
`NO_GO_BLOCKING_DEMAND_TRANSFER_4GIB_EVEN_OFFLINE_REPLACEMENT` is withdrawn
as an evidence-backed decision until the replay is reproduced under a new
identity with retained provenance.

## Historical inputs

The replay used:

- native routing trace SHA-256:
  `4462cfeba898ef1ffb8dd88c36b41ad03e723b6e6b3d2bc31365fec98b00cd35`;
- admitted native expert inventory:
  - 24 MoE layers;
  - 32 experts/layer;
  - 13,253,760 encoded bytes/expert;
- frozen `min_graph_seq=1`;
- 16 GiB hypothetical RAM tier;
- 4 GiB hypothetical VRAM tier;
- 324 equal expert slots at 4 GiB.

The trace contains 1,440 one-token expert accesses.

## Locality result

At 4 GiB:

- byte-LRU VRAM hit rate: 66.250000%;
- equal-slot LRU(324) hit rate: 66.250000%;
- Belady offline oracle(324) hit rate: 70.208333%.

Belady is non-causal and is only an offline upper bound on hit rate/lower bound
on loads for equal-sized slots.

## Crossover comparison

The admitted k=1 expert crossover measured:

- CPU path: 0.356471 ms;
- resident-GPU path: 0.061410 ms;
- pinned cold-GPU path: 1.0882936 ms.

The idealized serial blocking-copy cache break-even is:

`p = (cold_gpu - cpu) / (cold_gpu - resident_gpu)`

which gives 71.266364%.

Therefore:

- LRU is 5.016 percentage points below blocking-copy break-even;
- even Belady is 1.058 percentage points below blocking-copy break-even.

## Decision

`HISTORICAL_NO_GO_BLOCKING_DEMAND_TRANSFER_4GIB_EVEN_OFFLINE_REPLACEMENT_NOT_ADMITTED`.

For this trace and 4 GiB capacity, even a non-causal equal-sized Belady cache
cannot provide enough hits to rescue the serial policy:

`miss -> copy weights synchronously -> execute GPU`.

The historical arithmetic suggested the prior architectural decision, but this publication no longer strengthens it as admitted evidence.

The surviving policy remains:

- resident GPU hit -> GPU expert compute;
- GPU miss -> CPU expert compute;
- Host->GPU transfer only as anticipatory residency/prefetch work.

## Idealized GPU-hit / CPU-miss arithmetic headroom

Using the measured k=1 medians and trace-derived hit rates:

- LRU(324): 0.160993 ms/expert;
- Belady(324): 0.149314 ms/expert;
- always CPU: 0.356471 ms/expert.

Relative to always-CPU, the arithmetic LRU diagnostic is about 54.8% lower
latency, or 2.21x throughput-equivalent on this isolated serial per-expert
model.

The Belady arithmetic diagnostic is about 58.1% lower latency, or 2.39x.

These are **not measured mixed-residency timings**. They ignore partitioning,
aggregation, scheduling, concurrency/serialization and full-model effects.

## Next discriminating gate

First reproduce the locality replay with retained commit/tree, command, raw output and hashes. Only after that gate is admitted should a real mixed-residency top-4 expert
FFN through pinned ggml with:

- 0 resident GPU experts / 4 CPU experts;
- 1 GPU / 3 CPU;
- 2 GPU / 2 CPU;
- 3 GPU / 1 CPU;
- 4 GPU / 0 CPU.

Use the same real expert shape and CPU buffer authority as the admitted
crossover.

The first mixed gate should be serial/fail-closed and validate numerical parity
against the all-CPU reference. Only if measured mixed residency retains useful
headroom should a parallel/overlapped mixed path or prefetch policy be tested.

## Claim boundary

The locality values are trace-derived cache simulation over encoded expert
payload sizes, not measured runtime memory traffic. The arithmetic hybrid
latencies combine independent measurements and simulation; they are not
measured mixed-residency layer latency, full-model speedup or physical
PCIe/DRAM/NVMe traffic.
