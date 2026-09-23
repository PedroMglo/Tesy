# B0/B1 stock placement diagnostic protocol

Date: 2026-09-23
Base: `research/first-real-bringup-20260923@82551a89a8f2625d5191012a8d96bc7a4cf4996a`
Branch: `research/b0-b1-stock-placement-telemetry-20260923`
Classification: prospective diagnostic

## Decision from first bring-up

The first real trace established:
- 24 x 32 expert objects;
- 13,253,760 encoded payload bytes per expert;
- 429 unique layer/expert keys in 15 decode steps;
- meaningful LRU/Belady headroom in VRAM-sized slot counts;
- 16 GiB simulated RAM cache had zero evictions because the observed unique
  expert working set was only ~5.69 GB.

Therefore gpt-oss-20b does **not** test a >RAM hot decode path. Its immediate
question is RAM/CPU versus GPU residency/compute.

No native Tesy expert cache is authorized yet.

## Arms

B0:
stock llama.cpp automatic placement.

B1:
same stock backend and settings plus `--cpu-moe`.

No Tesy runtime modification is present in either arm.

## Frozen model/backend

Same locked gpt-oss-20b MXFP4 GGUF and llama.cpp pin as the successful bring-up.

The local CUDA/GCC toolchain must match the recorded bring-up identity unless a
new prospective amendment is committed before execution.

## Workload

- committed prompt: `benchmarks/prompts/b0-b1-diagnostic.txt`;
- context: 4096;
- parallel requests: 1;
- generated tokens requested: 64;
- temperature 0;
- top-k 1;
- seed 42;
- prompt cache disabled;
- fresh server process for every repetition;
- server warmup disabled;
- 12 CPU threads / 12 batch threads;
- automatic GPU layer fit with 1024 MiB target headroom.

Order:
`B0, B1, B1, B0`.

This balances first/last order but is still diagnostic, not a confirmatory
performance campaign.

## Measurements

Per fresh process:
- model/server ready wall time;
- request TTFT measured client-side to first non-empty SSE content;
- server `prompt_n/prompt_ms/prompt_per_second`;
- server `predicted_n/predicted_ms/predicted_per_second`;
- exact 64 generated token IDs and SHA-256 trajectory identity;
- total request wall time;
- peak observed GPU memory used;
- peak process VmRSS/VmSwap;
- minimum system MemAvailable/SwapFree;
- GPU temperature/pstate/power samples where available;
- source/backend/model identities, with backend source HEAD enforced against the lock;
- non-empty placement/load log excerpts.

Do not call nvidia-smi sample bytes PCIe traffic.

## Stop rules

Stop an arm/repetition on:
- server non-zero exit before requested completion;
- model/backend identity mismatch;
- missing final server timings;
- no streamed content/TTFT;
- OOM;
- server process swap > 0;
- non-finite timing;
- corrupted/missing required telemetry;
- generated-token trajectory mismatch across B0/B1 or fewer than 64 generated IDs.

A failed repetition is preserved. Debugging uses a new campaign identity.

Intermittent auxiliary nvidia-smi sample failure is retained in telemetry; if
GPU peak cannot be established, resource evidence is INCONCLUSIVE rather than
silently PASS.

## Interpretation

B0/B1 identifies the strongest stock execution boundary for the next phase.

It does not measure:
- physical NVMe expert bytes;
- physical PCIe expert bytes;
- benefit of a Tesy cache;
- >RAM behavior;
- speculative benefit.

After B0/B1, the next cheap gate is CPU-resident expert compute versus
RAM->GPU transfer+compute versus already-resident GPU compute using real expert
shapes. Only then decide whether a native cache/prefetch mechanism is justified.


## Review amendment

The original runner recorded timing without retaining generated token IDs and
treated placement log extraction as optional. That is no longer admitted.

The runner now:
- executes the pinned backend provenance probe before model measurement;
- requires non-empty placement telemetry for every fresh process;
- records exactly 64 generated token IDs per observation;
- stops on the first trajectory mismatch across the four B0/B1 runs.

Older B0/B1 results produced without these gates are diagnostic only and must
not be promoted as an identical-trajectory placement comparison.
