# C98 ledger

- Code/freeze: `488436e`, `ea7aec9`. Model-free TIME_WAIT regression and resource tests: 16/16 PASS. Host inventory: 60 s, E18 admitted.
- C97 control run: `c97-control01`, measurement `586aa54`, PASS 2/2. C98 candidate run: `c98-candidate01`, measurement `ea7aec9`, PASS 2/2. Both used `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0` with the frozen Python runner. Raw hashes are in `manifest.json`.
- Equal official prompt IDs and complete assistant messages on both turns; second turn cache_n=2044/2081 in both. Cold prefill 275.913 → 68.211 s; warm prefill 9.626 → 6.834 s. Cold request wall 300.398 → 92.538 s; warm request wall 28.646 → 25.500 s.
- No resource stop or swap. One sequential pair gives a bridge, not a confirmed performance claim. Synthetic history is not a diverse quality test. M3 remains partial; M4 not met.
- Preserved failures: C48 and C78 unchanged; C96/C97 candidate prelaunch attempts did not load a model and remain FAIL_HARNESS_PRELAUNCH. Next: alternating server screening with fresh pairs and frozen start criteria.
