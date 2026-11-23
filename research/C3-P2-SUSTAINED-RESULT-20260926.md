# C3 P2 next-wave preload: sustained service result

Evidence class: **MEDIDO_NO_TARGET**, scoped to the GPT-OSS 120B GGUF MXFP4 (`582bd40f…0c622d`), freedomljc backend `1248fd8…9d5`, GPU8/32 slots/context4096/b256/ub32, medium greedy seed42. Run `c3-p2-preload-sustained20-01` followed the prospectively frozen [protocol](C3-P2-SUSTAINED-PROTOCOL-20260926.md). The only runtime change from the C2 32-slot profile was enabling its existing next-wave preload. Run and publication gates: PASS; 20/20 fixed requests, all IDs/tokens/timers/telemetry present, no backend stop, no swap/OOM/max events or resource guard violation. This is a **production-path service gate within the C3 boundary coverage**, not full independent-model numerical parity.

| Metric | C3 preload | C2 no-preload historical |
|---|---:|---:|
| Requests / completion tokens | 20 / 4588 | 20 / 4588 |
| Process / active wall (s) | 2116.148 / 2110.553 | 2156.499 / 2150.689 |
| Aggregate prefill (s) | 716.442 | 771.409 |
| Aggregate decode (s) | 1393.946 | 1379.108 |
| Decode (tok/s) | **3.291376** | 3.326788 |
| Last ten (tok/s) | **3.258553** | 3.289640 |
| Truncated at cap | 2 | 2 |

The C3 run met its >=3 tok/s aggregate and late gates over 1393.946 s of actual decode and 2110.553 s of active requests. It did **not** reach 4 tok/s. The historical comparison suggests prefill 54.967 s lower but decode 14.838 s slower; different run dates, thermal/cache conditions and processes mean this is **not a causal sustained A/B**. Paired C3 prefill trials provide the causal A/B (median -17.515% for 496 IDs and -18.240% for 1522 IDs), below the frozen -25% engineering goal. All 20 raw assistant reasoning/final contents, finish reasons and API token counts match the C2 no-preload control exactly. The two cap-truncated answers remain failed task completions in cost accounting.

Measured peak cgroup memory 14,923,575,296 B, sampled RSS HWM 15,068,581,888 B, GPU 3867 MiB; zero runtime swap and zero local/hierarchical max/OOM/kill deltas. CPU maximum in 300 s windows 87.375 C, GPU 57 C, NVMe composite 58.85 C, under frozen 95/80/70 C guards. `/proc` read_bytes and encoded payload are not exclusive physical NVMe traffic. Backend decode includes waits but excludes prefill and idle. Per-token p50/p95 and time to first final content are **NOT_MEASURED** by this nonstreamed protocol.

Decision: retain the C2 no-preload sustained profile as the conservative default. Preload is a **qualified opt-in for long-prefill workloads within the tested scope**: it preserved exact outputs and >=3 tok/s sustained service but missed the 25% prefill and 4 tok/s goals, and its sustained decode was slightly lower than historical control. No automatic promotion to a universal or daily-use default. A future same-day sustained A/B would be needed for a causal service-level speedup claim.

Compact evidence: `results/c3-p2-preload-sustained20-01.gate.json`, `results/c3-p2-preload-sustained20-01-analysis01.json`, `results/c3-p2-preload-sustained20-01.published.json`, `results/c3-p2-preload-sustained-comparison01.json`. Raw stdout/stderr, samples, preflight/launch/raw/normalized are immutable local files under the same run prefix; the publication lists their SHA-256 hashes. Exact tested launch:

```sh
systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- python3 tools/c2_server_run.py --model target120b --suite c3sustained20 --ngl 8 --ubatch 32 --slots 32 --protocol-id c3-p2-preload-sustained20-v1 --protocol workloads/c3_p2_preload_sustained20_protocol.json --run-id c3-p2-preload-sustained20-01
```
