# C236 — block verification and reuse between prefill tiles

## Authority and current state

Owner delivered post-C235 version1.0. Its repeated delivery is one authority,
one epoch; no historical balance transfers. Base/origin was re-observed at
`8c78f598e446b1b09fb3ba518b77e0d7496bfa47`; the dedicated branch is
`campaign/120b-block-verifier-expert-reuse-20261004T105527Z`.
C235 closed LOCAL_ONLY, then the owner authorized its publication. That
historical closure is preserved. This epoch permits local commits only.

Research clock starts conservatively at2026-10-04T10:49:00Z, before the first
recorded readonly timestamp10:50:11Z. The seven-day deadline is2026-10-11T10:49Z.
120 active hours /16 physical hours /12GiB raw /20GiB derived are ceilings.
12 active hours and4 physical hours remain reserved for confirmation,
qualification and closure. The existing ledger receives a prospective active
session clock; older elapsed-wall epochs retain their interpretation. An open
session charges elapsed time conservatively; reboot requires reconciliation.

## Reconciliation — SOURCE_AUDITED / observed host, not numeric qualification

The historical `/tmp/tesy-c75-backend-20260928` disappeared after reboot.
No original executable/library identity is inherited. A private source checkout
at freedomljc/llama.cpp1248fd8… plus the stored C35 and C75 patches reproduces
**exactly** historical source tree`45b2b5b97353845d9d982a06f20c4f2f420528e2`.
Reconstruction commit`092a57f7` and its new binaries are a distinct build.
Compiler/toolchain/libs and a bridge against preserved references are required
before performance claims. No shared backend or ordinary service is modified.

Observed HX370/24 threads, RTX4060Laptop8188MiB, RAM32698781696B,
swap16348868608B unused; existing Ollama service has no observed model runner.
The GPU reports implausible power590W against75W; optional power is UNKNOWN,
not measured energy. Device-derived mandatory guards still require live policy.
Model inode/size/mtime/ctime match the preserved identity; no new full-weight
hash scan is claimed. Disk initially has about404GB free on NVMe/btrfs.

Initial configure failed because nvcc inherited an unsupported default compiler.
Prospective repair pins CUDA host g++15 explicitly; no unsupported-compiler
override. Its failure remains in the new raw/build record. No weights loaded.

## Boundaries and next discriminants

A: source sampler compares each target sample with its proposed token until the
first rejection; all-accept samples one bonus. B positions=K+1 include the known
anchor as input, not another output. Server speculative indices must fit its
sub-batch. Last-layer out_ids must include every verifier row. Start with one
sequence, B2/4/8, prefillub32, greedy only, all necessary logits materialized.
R0 is autoregressive C75. An R1 claim must be independent of rejected future
proposals; fixed shape alone is not assumed to prove this.

B: reuse the validated journals, routing and before-prefill snapshots. Pools
are per layer; other layers do not directly evict a layer's expert slots.
Measure repeated demand/preload loads separately from expert unions and
initial ready/in-flight work. Bytes are logical, not physical NVMe traffic.
Only a material time scenario admits expert-major multi-tile prototyping.

The next physical unit is a bounded bridge for the rebuilt identity, then A1
numeric/causal block verification. B analysis proceeds using existing raw.
EAGLE weights remain NOT_RUN until the A1 economic/semantic gate passes.
No old numeric PASS, readiness NO_GO, FAIL or budget is edited.

## Current gates and limits

Five directed active-clock counterproofs pass model-free: distinct boots,
idle session gaps, overlap rejection, nonfinite/negative spans, and explicit
reboot reconciliation. Model correctness/blocks/performance: NOT_RUN.
Slots40 remains the historical opt-in profile, M3 PARTIAL and M4 NOT_MET;
its missing temporary runtime is an operational artifact limitation.
The final recipe must declare the new identity and its measured coverage.
