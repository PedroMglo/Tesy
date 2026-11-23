# C127 — slots40 numeric and forward admission

Objective: test whether the confirmed C75 P12 waves backend can use 40
expert slots per layer under the same E18/zero-swap envelope. This is a new
numeric profile: a 32-token ubatch can form up to eight waves instead of ten,
and decode residency changes. C35 remains the independent operational
control; C75/slots32 is the direct capacity comparator for any later timing.

Base: C126 result `692c153f9618d6aa758c90be0502dd99c591210e`.
Hypothesis: extra slots avoid a material fraction of exact decode expert
reloads while preserving useful output. Alternative: the hidden LFU state
already retains the useful experts, or larger pools/workspace overwhelm the
available RAM/VRAM and provide no useful latency gain.

Rationale is deliberately weak. In C123 warm153, 302 of 1509 observed decode
misses followed an observed eviction and no more than eight distinct later
reservations in that layer. The trace does not expose the previous request's
hotness or complete initial slot map, so this is an opportunity count, not
the counterfactual number of misses at 40 slots. A simple empty-start LRU
simulation badly missed the observed 32-slot baseline and will not be used
as a performance forecast.

The probe is a copy of C80 with only `slot_count` and
`mp.moe_stream_slots` changed from 32 to 40. Build output is on NVMe, not
tmpfs. The original C75 backend, GGUF, tokenizer, routing, medium effort,
P12 placement, ubatch32, preload, full SWA and F16 unified/offloaded KV
remain fixed. Fresh resource inventory/policy and exact binary/library
hashes are frozen before any model execution.

Static pool growth from the C123 layer metadata is 2,643,840,000 bytes CPU
and 1,163,289,600 bytes GPU. C126's observed peak plus the CPU increment is
well below E18 minus the initial 512 MiB cgroup margin; its observed GPU
use plus the GPU increment is below the GPU total-use guard, but these are
admission estimates. Allocation failure, new workspace, context or external
use can invalidate them. Measure allocation and a short forward before
larger shape/context claims.

Numeric gate: frozen 189+32 boundary, one OFF and one ON under slots40,
bitwise equality of all active routed states and full logits, valid parked
pairs/bytes, then independent resident recomputation of all 36 FFN layers
using the slots40 ON activations. All active router IDs/weights and FFN
outputs must match bitwise; nonfinite, aliasing, wrong expert, missing state
or resource stop is FAIL. This does not inherit independent attention/KV
validation or universal equivalence from C93/C94. Only after numeric and
forward admission may a new nominal153 timing screen be frozen.

Expected scope: two bounded capture processes plus 36 one-layer resident
reference processes, E18/zero swap, raw <512 MiB, no profiler. Freeze,
measurement and result commits are separate. Failures remain under their
identity; no defaults or remote writes.
