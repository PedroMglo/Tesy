# M3 target capacity: 24 versus 32 slots

Objective and prospective decision: `research/M3-CAPACITY32-PREFLIGHT-20260926.md`, based on lab commit `33c4804`; freeze checkpoint `381fb7f`. This was optimization/configuration intervention 4/6. The selected 120B MXFP4 GGUF, original streaming backend `1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5`, binary SHA-256 `422ff917448c9bb4cb3b59e9af75d9f0d8fc145ffa6c49317d722dd86aa14b94`, GPU8 placement, context4096, batch256/microbatch32, greedy sampler, two-turn workload, O_DIRECT expert reads and 18 GiB/zero-swap cgroup were fixed. Only the existing per-layer expert slot count changed. No backend source patch or speculative mechanism was introduced.

The numeric gate passed first: the saved 24-slot and new 32-slot GPU8 four-token probes used the same binary/model and had the same token IDs and all 201,088 final logits bitwise equal. This is limited fixed-prefix equivalence, not numerical proof for every later routed state.

Six new full-model runs followed the frozen order 32, 24, 24, 32, 32, 24. Every run completed both requests with the same 158 and 114 decoded token counts and identical response hashes across all runs. The first arithmetic answer passed; the existing second-request extraction-field failure remained. Full commands, identities, metrics and stop conditions are in the individual JSON manifests and `results/m3-capacity32-ab-summary.json`. Raw stdout/stderr and one-second samples remain local.

| Slots | Aggregate decode tok/s, three runs | Mean tok/s | Mean elapsed s | Mean sampled process read GB | Peak cgroup GB range | Total GPU MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 24 | 2.637, 2.592, 2.474 | 2.568 | 229.847 | 321.650 | 11.503–13.218 | 3112 |
| 32 | 3.266, 3.308, 3.235 | 3.269 | 185.831 | 259.517 | 14.604–15.538 | 3860 |

Measured mean aggregate decode gain was **27.324%**; mean end-to-end time decreased **19.150%**, and sampled process `read_bytes` decreased **19.317%**. All six runs exited normally with zero swap, zero cgroup `max` events, zero OOM events and no watchdog stop. The first 32-slot request decoded at 3.515–3.651 tok/s and the second at 2.906–2.926 tok/s. Neither four nor eight tok/s was achieved in this comparison. `read_bytes` is process accounting and cannot be relabelled exclusive physical NVMe traffic.

The 32-slot nominal encoded expert pool adds 2,961,100,800 host bytes and 846,028,800 GPU bytes compared with 24 slots. Observed cgroup peak reached 15,538,241,536 bytes and total GPU use 3860 MiB, inside the frozen guards; these peaks include overhead and depend on file/page accounting. No per-tier hit, H2D or eviction breakdown was added, so the lower reads support but do not fully isolate the cache mechanism.

Decision: retain 32 slots as the better **bounded two-request** configuration for this workload. Retain the original 24-slot configuration as the **sustained M5 validated** configuration, because no long 32-slot server run was performed. This is a second reproducible M3 capacity improvement within the measured scope, with no code change to revert. The separate 24-slot 22-minute result remains the only sustained >=2 tok/s claim. The next discriminating measurement, if a new campaign is authorized, is sustained 32-slot operation with the same task and resource gates; deeper per-tier instrumentation and broader fixed-prefix parity remain separate correctness/accounting questions. Tests: four-token bitwise gate and six full-model A/B runs passed; sustained 32-slot test NOT_RUN.
