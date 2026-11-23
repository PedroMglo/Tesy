# C52b sustained assistant-history ledger

- Measurement commit `29602ba6f3be24dc18c73e949e900ca185df1436`; one `systemd-run --user --scope` E18/zero-swap execution, no retry. C52 abbreviated-SHA prelaunch FAIL preserved.
- 20/20 requests, 19/19 adjacent exact-prefix gates, 4227.64 s session span; prompts 2043→4969 IDs; responses repeat the first synthetic five-digit answer.
- First/last ten wall medians 41.66/42.58 s; decode medians 3.67/3.83 tok/s. Incremental first-final median 41.46 s; prefill/decode medians 25.92/16.29 s.
- E18 PASS: CPU max 95.125 °C warning, GPU 63 °C, NVMe 54.85 °C, GPU 5752 MiB, RSS 13.31 GB, zero swap/OOM; no cooling state. No own model process remains.
- M3 session mechanics tested in this synthetic scope; M4 latency/decode targets not met; default unchanged. Raw local only, hashed in manifest.
- Next: C53 model-free attribution of incremental prefill/decode cost, then one bounded diagnostic if it changes the mechanism choice.
