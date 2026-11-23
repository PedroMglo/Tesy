# Architecture and explicit limitations

## What executes today

Python CLI → strict file/contracts → GGUF inventory / replay / bounds / model identity.
The native F32 cache is a separate, tested primitive, not secretly injected into
stock chat. The chat command optionally starts the locked stock llama.cpp binary;
stock owns tokenization, template, routing, attention, KV, sampling and output.
No cache result or predictor substitutes a target expert.

## Routing trace v1

See `examples/routing.synthetic.json`. Root keys are exact: schema, session_id,
provenance, layers, experts, events. One trace equals one session; each replay
starts with empty caches and a fresh predictor. There is no cross-session leak.

Provenance kind is SYNTHETIC with null model hash or OBSERVED with a SHA-256.
This is a syntactic claim from the producer, NOT cryptographic proof a model ran.
`route_semantics` must be sequential_target. Every token has exactly the supplied
ordered layer list; token IDs in this format mean absolute positions, not
vocabulary IDs. Steps start at zero and increase by one. Routed experts are
unique within an event and validated against `(layer, expert)` inventory IDs.

Inventory `bytes` means the encoded complete expert payload at the chosen
transfer granularity. A real collector must derive this from all relevant
expert matrices and actual strides; do not divide a tensor by expert count
without checking its layout. The parser currently does not do that derivation.

Do not use reference-route events to drive a future online candidate's routing.
The eventual candidate must run its own router. A benchmark needs producer
identity, clean commit, model hash, collector binary hash and workload provenance
in a separately authenticated publication.

## Replay semantics

Each event executes expert demands sequentially in router order, not as parallel
experts. Objects are immutable. GPU and RAM caches are non-inclusive: evicting
RAM does not invalidate a GPU copy, and evicting GPU needs no writeback. A GPU
miss reads RAM if resident, otherwise reads the source into a separately reserved
host staging area and optionally admits to RAM. Then it transfers to GPU.
An expert too large for RAM bypasses RAM; too large for GPU/staging rejects the
plan because this replay does not model CPU fallback or tiled expert loading.

There is no hidden prefetch overlap. `transition` learns only completed same-layer
route transitions from this session, predicts from the current observed tuple,
and synchronously prefetches at most one new expert. It can evict useful objects.
The resulting byte cost includes bad predictions and never becomes tok/s.
`lfu` counts references while resident and breaks ties by recency; this is not
global LFU or a claim to optimally solve heterogeneous caching.

Counters `source_request_bytes` and `h2d_payload_bytes` are simulated requests.
They are NOT measured PCIe traffic or physical NVMe reads. `serialized_copy_estimate_ns`
uses explicit assumed/reference bandwidths; it omits compute and does not model
overlap. CPU quantized compute, bus contention, page cache, alignment, DMA launch
cost and graph deadlines remain outside this first replay. These limits block a
production scheduling decision, not the deterministic software tests.

`union --k K` computes bytes in the union of a sequential target trajectory.
Its windows include a final partial tail. It says nothing about draft accuracy,
rejected branches, actual cache misses, accepted tokens or attainable speedup.
No offline oracle selector is implemented or mislabeled as an online policy.

## Transport planner

Each tier declares bytes per committed token and a bandwidth classification.
`MEASURED_REFERENCE` is not a hard ceiling. Only `UPPER_BOUND` can produce
`NOGO_HARD_TRANSPORT_BOUND`; both require justification/provenance external to
this arithmetic helper. No bound violation yields `NOT_EXCLUDED_BY_TRANSPORT`,
never a performance PASS. Missing bandwidth yields INCONCLUSIVE. This helper
cannot certify the realism of caller-supplied traffic or a fabricated bound.

## File and metadata boundary

`io.py` limits JSON size/depth and rejects duplicate keys/non-finite values.
`gguf.py` consumes at most a bounded metadata prefix; no tensor data is read.
It validates dimensions, explicit quantization block sizes, aligned spans and
no overlap. Header SHA-256 is NOT the full model SHA-256. Full model identity
is a separate streaming read in `models verify`.

Trusted parent directories are required. Canonical-path and no-follow checks
reject observed symlinks, while same-FD identity checks detect mutation/replacement.
This is not a sandbox against an attacker continuously renaming parent directories.
Model FD handoff in Linux prevents path replacement during stock launch; source
files must remain read-only/immutable throughout use. A pinned commit printed by
`--version` is not alone a supply-chain attestation; retain the build/dependency
manifest before any scientific benchmark.

JSON publication uses temp + fsync + hard-link no-replace + parent fsync + readback.
No unsafe overwrite fallback. A failure after publication leaves the final file
for investigation, rather than deleting evidence. Parent-directory security is
an operator responsibility. Outputs are data-only, never commands to execute.

## Native primitive

See `native/README.md`. State is synchronous: reserve/reclaim → load → publish
resident → hold lease → reclaim only when unleased. Failed admission due to
pinned capacity leaves cache entries intact. I/O/mutation poisons the store;
caller output changes only after successful compute and final identity check.
This validates ownership but not asynchronous CUDA event ordering.

## Planned next integration (not existing code)

First instrument native natural routing on the locked qwen3moe graph; do not
reimplement a Transformer. Validate expert IDs, tensor spans, positions and
collector overhead against an independent observation. Next connect demand
residency without prediction, compare all logits/tokens/routing/required KV with
a frozen stock reference, and only then benchmark. CPU/GPU numerical paths need
separate contracts: do not call tolerance parity bitwise exactness.

Progression: trace → real-byte replay calibration → demand-only integration →
exactness → costs → causal policies → speculation only if evidence supports it.
