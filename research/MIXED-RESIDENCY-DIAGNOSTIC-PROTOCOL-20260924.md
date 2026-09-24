# Mixed GPU-hit / CPU-miss diagnostic protocol

Date: 2026-09-24  
Branch: `research/mixed-residency-diagnostic-20260924`  
Classification: staged diagnostic; grouped locality gate first

## Motivation

The admitted expert crossover and cache replay establish:

- blocking demand transfer is `NO_GO` at 4 GiB even against Belady offline;
- resident-GPU expert execution is much faster than the authoritative
  `--n-cpu-moe` CPU path;
- 4 GiB LRU still provides 66.25% expert hits on the measured routing trace.

The surviving architecture is:

`GPU hit -> GPU expert compute`

`GPU miss -> CPU expert compute`

with Host->GPU expert transfers used only to prepare future residency, never to
block the current miss.

Before implementing that execution path, determine which mixed top-4
compositions actually matter on the measured trace.

## Stage A: grouped residency opportunity

Replay the same admitted one-token trace and native expert inventory with the
same 4 GiB byte-LRU capacity and `min_graph_seq=1`.

For every routed layer/top-4 group, record how many of the four experts are
already resident immediately before their accesses:

- 0 GPU-resident / 4 CPU-miss;
- 1 GPU / 3 CPU;
- 2 GPU / 2 CPU;
- 3 GPU / 1 CPU;
- 4 GPU / 0 CPU.

The LRU state is updated on misses exactly as in the existing demand-triggered
simulation.

Important boundary: this grouped replay assumes a miss can be inserted for
future accesses without delaying the current demand. It therefore describes
**residency opportunity under ideal timely insertion**, not a production
prefetch implementation or measured cache state.

The aggregate expert hit rate must equal the existing admitted byte-LRU replay.
A mismatch is a bug.

## Stage B: physical mixed top-4 measurement

Only after Stage A identifies the material hit-count cases should Tesy measure
mixed execution physically.

For a chosen top-4 group, use real admitted expert tensors and the same pinned
ggml FFN semantics as the crossover.

For `h` resident GPU experts:

- execute those `h` experts on CUDA;
- execute the remaining `4-h` experts on the authoritative CPU default
  buffer path;
- preserve the same deterministic input and expert weights;
- preserve one global top-4 mixture coefficient per expert;
- return the final aggregated 2880-F32 result on GPU.

The first implementation should be serial/fail-closed:

1. GPU -> Host input activation if CPU misses exist;
2. CPU-miss expert FFN;
3. Host -> GPU CPU partial output;
4. resident-GPU expert FFN;
5. GPU aggregation.

Do not introduce concurrency yet. The point is to validate actual partition,
aggregation overhead and numerical parity against an all-CPU top-4 reference.

Only if this serial mixed path preserves useful headroom should a concurrent
CPU/GPU overlap experiment be justified.

## Correctness

For every measured `h`:

- all outputs finite;
- compare final mixed result against the all-CPU top-4 result;
- freeze numerical thresholds prospectively before physical timing;
- preserve exact expert tensor bytes and deterministic expert IDs.

This is numerical parity of one isolated expert FFN, not Transformer/token
equality.

## No prefetch yet

Do not implement a predictor, prefetch queue, eviction scheduler or custom
loader in this stage.

A prefetch mechanism is justified only after:

1. grouped locality establishes useful target cases;
2. direct mixed execution retains a meaningful advantage after partition and
   aggregation overhead;
3. wasted-prefetch tolerance can be bounded against measured transfer cost.

## Claim boundary

Stage A is trace-derived residency opportunity, not measured cache residency.
Stage B will be an isolated mixed expert-FFN diagnostic, not full-model Tesy
speedup. No requested-copy byte is physical PCIe traffic.
