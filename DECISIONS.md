# Decisions and A/B ledger

| Time (Europe/Lisbon) | Hypothesis/change | Result | Decision and reason |
|---|---|---|---|
| 2026-09-26 00:44 | Use a sibling lab at the requested path | Path absent and outside authorized writable roots | Create a separate nested Git repo inside the authorized Tesy root; do not alter its branch or tracked files. |
| 2026-09-26 00:49 | Use stock llama.cpp and one expert streaming branch | Immutable SHAs resolved and cloned; no run yet | Keep stock independent and compare the candidate with streaming off/on before a practical cross-version comparison. |
| 2026-09-26 00:50 | Configure CUDA with default GCC 16 | CMake compiler identification failed: CUDA 13.3 rejects GCC >15 | Use installed GCC 15 for both backends; no system toolchain changes. |
| 2026-09-26 00:52 | Stream 120B native safetensors directly through candidate | Source accepts GGUF model loader and GGUF offsets | Incompatible artifact format for this candidate. Do not convert or download automatically. |

The rows above record decisions made before model execution. Executed A/B results and failures follow.

## Executed decisions and comparisons

| Order | Hypothesis/change | Evidence and result | Decision |
|---|---|---|---|
| A1 | Candidate plain CPU with default repacking versus streamed CPU | Fixed 17-token prefix: max logit difference 0.306599, RMSE 0.057832, only 9/10 top tokens shared; `CPU_REPACK` applied to plain expert weights but streaming used ordinary CPU buffers | **FAIL as a parity comparison**. Keep the raw result. Align buffer/kernel settings in a new diagnostic run; no threshold widened. |
| A2 | Same SHA, CPU buffers and microbatch with repacking disabled | 201,088/201,088 logits bitwise equal at `ubatch=1` and `ubatch=32`; the latter ran 83 non-empty waves and 440 cold misses | Numerical gate passes for these two fixed-prefix cases only. |
| A3 | Stream 20B under 9 GiB host cgroup with CPU cache 16/32 slots per layer, O_DIRECT and no swap | Two requests in one process, 195 and 193 decode tokens, natural EOS, validated outputs; cgroup peak 7.35 GB, no swap/OOM/limit events. CLI FD inspection in a separate run found an O_DIRECT model descriptor while decoding | M1 surrogate mechanism retained. It proves controlled-budget streaming for 20B, not 120B performance. |
| A4 | Compare CPU streamed with same-SHA plain, `--no-mmap --no-repack`, same two turns | Both response texts byte-identical. Decode 7.40/5.83 tok/s streamed vs 23.12/22.80 plain. Plain cgroup peak 12.67 GB under 16 GiB limit. An earlier default-mmap plain run charged only 1.75 GB to its cgroup despite 12.34 GB RSS because of shared page cache | Retain honest negative A/B. Do not treat warm shared page cache accounting as proof of over-budget stock execution. |
| A5 | GPU8 numerical comparison with loader direct I/O but default op offload | Max logit difference 0.408554; streaming disabled op offload automatically for host cache while plain kept it enabled | **FAIL as a parity comparison**. Equalize op offload in a new diagnostic run. |
| A6 | GPU8 plain attempt under 16 GiB cgroup | `memory.events max` increased 1271 times; runner marked `CGROUP_LIMIT_HIT` though the process returned 0. `CUDA_Host` buffer 7.93 GiB plus file cache caused duplicate host accounting | Resource failure preserved. Use a new run identity with loader direct I/O and explicit headroom. |
| A7 | Same-SHA GPU8 reference and stream, no repack, no op offload, direct loader, `ubatch=32` | 201,088/201,088 logits bitwise equal; stream log shows 440 cold misses, 83 non-empty waves, O_DIRECT active | Numerical gate passes for the one GPU fixed prefix. Long GPU generation is functional but has no full-token numerical reference. |
| A8 | Practical 20B comparison at 9 GiB host cap | Candidate GPU8 decode 9.24/6.75 tok/s, GPU peak 2423 MiB; stock GPU14 decode 45.50/43.88 tok/s, GPU peak 6589 MiB; both answer tasks, zero swap/OOM. Different backend SHA, placement and generated lengths | Stock is faster on this **20B** workload. No target or sustained-performance claim. |
| A9 | Local server with GPU8 candidate | Bound to `127.0.0.1`, `/v1/chat/completions` returned final `12` in 44 tokens, server stopped after request | Keep tested localhost command for surrogate reproduction. |

Optimization-intervention budget consumed: 2/6 diagnostic configuration interventions (GPU placement trial; direct loader after resource failure). Neither is promoted as a reproducible M3 throughput optimization. No backend source patch was retained or reverted.

## Resumed 120B campaign (2026-09-26, local time)

| Time | Hypothesis/change | Evidence and result | Decision |
|---|---|---|---|
| 10:57 | Existing 16-slot stream can bring up verified 120B GGUF under 18 GiB host / zero swap | `target120b-gpu8-smoke01`: 8 tokens, 2.68 decode tok/s over 2.98 s, 11.34 GB peak cgroup, 2406 MiB peak total GPU, direct expert FD, no swap/OOM | Bring-up smoke passes; sustained performance and correctness remain open. |
| 11:01 | Four-token same-SHA `mmap`/stream probe under 9 GiB is feasible on 20B | `probe20b-prefix4-plain01` stopped at 9.72 GB RSS (`RSS_GUARD`), zero swap/OOM | Keep resource failure; new 16 GiB diagnostic identity used because 20B is 12.11 GB total. |
| 11:02 | New 16 GiB plain 20B probe versus stream probe | `probe20b-prefix4-compare01`: 201,088/201,088 logits bitwise equal, same four token IDs | Tool diagnostic validated for this small prefix; prior 9 GiB failure remains. |
| 11:03 | 120B four-token plain `mmap` reference can load under 18 GiB | `probe120b-prefix4-plain01` stopped at 19.79 GB RSS during load (`RSS_GUARD`), before logits. Source `init_mappings(true)` calls `MAP_POPULATE` over full 63.39 GB file. Stream counterpart completed. | No target numerical parity claim yet. Prepare isolated diagnostic build changing only the `mmap` prefetch flag; keep original backend and failed reference intact. |
| 11:13 | Diagnostic copy disables only mmap prefetch under an explicit environment flag | Patched SHA `e5230b9`. On 20B, four-token plain logits equal original unpatched plain 201,088/201,088 bitwise; on 120B, four-token plain and original streamed logits equal 201,088/201,088 bitwise. 120B reference peak 12.72 GB cgroup, zero swap/OOM. | Retain patch only as a bounded reference tool. Proceed to two-request target test. This does not validate later decode states or sustained speed. |
