# C52b — sustained assistant-history result

- Objective: qualify the C51 actual assistant-history server path over 20 requests and at least 60 minutes.
- Base/measurement commit: `29602ba6f3be24dc18c73e949e900ca185df1436`; clean P12 8K E18 source, binary, model and input hashes in the frozen protocol.
- Evidence class: one measured physical-host run with completed raw receipt, official tokenization, per-process resource samples and mapped backend library hashes. No statistical performance confirmation or independent full-model numerical reference.
- Alternative tested: growing assistant history could lose exact-prefix reuse, response continuity, output reserve or resource stability. All 20 requests completed; the 19 adjacent generated-token-aware cache gates passed. Session span was 4227.64 s.
- Timings: first/last ten request wall medians 41.66/42.58 s; decode medians 3.67/3.83 tok/s. Incremental median prefill 25.92 s, decode 16.29 s, and first final content 41.46 s. First/last prompt counts were 2043/4969 IDs.
- Resources: CPU 95.125 °C maximum, a warning under the CPU100 protocol; no cooling state. GPU 63 °C and 5752 MiB maximum; NVMe 54.85 °C; RSS 13.31 GB; zero swap/OOM. The server exited and GPU returned to 12 MiB with no compute app.
- Decision: `SESSION_PROFILE_PARTIAL`. M3 session mechanics passed this synthetic 20-request/70-minute scope, alongside the earlier C42 8K boundary and C40 functional suite. M4 proposed latency and decode goals remain unmet; default unchanged.
- Tests: 14 focused model-free tests and source syntax passed before measurement. The receipt validator checked sample cadence, endpoints, process identity, cgroup events and mapped libraries. Raw and thermal series remain local with SHA256 values in the manifest.
- Failures preserved: C52 abbreviated-SHA prelaunch, C47 assertion, C48 same-profile mismatch, C49 idle admission, C50 cache gate, and earlier CPU95 thermal protocol stops. None were reclassified.
- Limitation: one synthetic code-repetition task is not broad utility, p95/p99 or an output quality claim. The 20 turns share warm expert pools and page cache; these timings are not independent cold starts.
- Next discriminating gate: C53 model-free attribution of the observed incremental prefill and decode costs against existing C46 wave evidence. Freeze a bounded physical diagnostic only if it resolves the I/O-wait versus CPU-wave explanation.
