# C124 — nominal153 server confirmation

**Result: `CONFIRMED_OPERATIONAL_NOMINAL153` in the frozen synthetic assistant-history workload.** Source commit `e46c4ed16a6ffe4cc6004b50e39f4fa109935caf`; freeze/measurement commit `6d7c600603c4507be1ffdcd5da745a3f5472a293`. Six new server processes, in three alternating pairs, passed the strong per-arm 60 s inventory and actual Popen freshness gates, E18/swap0, model/backend/library identity, response/prefix/token validation, normal finish and resources. No usual service or default was changed. All raw remains local under `results/c124-nominal153-confirm-20260929T1515Z/raw/`, with file hashes in `manifest.json`.

| Metric | C35 median | C75 median | Median paired gain |
|---|---:|---:|---:|
| Warm first final content | 39.626 s | 25.180 s | **36.454%** |
| Warm prefill | 26.647 s | 12.380 s | 53.543% |
| Warm decode duration | 13.290 s | 13.242 s | 0.596% |
| Cold first final content, ~2K IDs | 301.728 s | 93.753 s | 68.928% |
| Cold prefill, ~2K IDs | 277.143 s | 68.771 s | 75.186% |
| Cold decode duration | 25.231 s | 24.999 s | −1.126% |

The three individual warm first-final gains were 36.260%, 36.640% and 36.454%; all positive and above the predeclared 8% confirmation median. The four protected timing medians all exceeded the −5% floor. In every arm, the first request had 2043 official prompt IDs and 78 output tokens; the second had 2197 prompt IDs, 2044 cached and **153 new**, followed by 47 output tokens. The inherited validator checked the expected answer and response relationship, stream completion, frozen fixture, and identity. Pair order and start temperatures are recorded in `timing-pairs.json`; operational warm start deliberately did not impose 3/3/2 °C matching. That limits causal attribution to the profile comparison under this operational regime and does not prove identical cache/thermal distributions.

**Scope and product:** C75 waves is now confirmed for this repeated-code nominal153 server task, with same-profile numerical support from C93–C95 and C123's diagnostic canary in their frozen boundaries. This does not erase C100 `NO_GO_CONFIRM` for its different server contract, C117 `FAIL_RESOURCES_OR_EVIDENCE`, or C122's canary crash. It does not establish diverse conversation, active sustained load, 7936-token boundary or the quality holdout for C75. M3 remains at C52b's tested session scope. M4 remains **NOT_DEMONSTRATED**: even this confirmed candidate's median first final is about25.18 s versus10 s, and 47 tokens over13.242 s is about3.55 tok/s versus6. Cold~2K prefill is not cold512.

**Next discriminant:** C123 measured 10.646 s of readiness wait in13.046 s of decode calls, with read union10.013 s and only0.047 s summed accepted-load queue delay. A fixed-stream completed-load 3 GiB global LRU saved only4.11% of decode loads. Test read parallelism of the three already authoritative expert components model-free using the same GGUF/trace offsets; proceed to a bounded backend prototype only if the discriminator is material and safe. Qualify diverse/long-session utility on the best surviving profile, within the same epoch budget. No remote publication is authorized by the current order.
