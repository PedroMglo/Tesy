# C100 ledger

- Measurement commit: `6850b366dda058fc123ef5a70b6226a3ce1ff708`; C35 control and C75 wave-skip candidate, 8K P12 server, same frozen two-request input.
- Command per arm: `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c100_server_wave_confirm.py run results/c100-server-wave-confirm-20260928T2211Z --run-id <RUN_ID> --measurement-commit 6850b366dda058fc123ef5a70b6226a3ce1ff708`. Order: p1 control/candidate, p2 candidate/control, p3 control/candidate.
- All six arms passed identity, complete responses, exact-prefix and resource gates; no swap or stop reason. `tools/c100_analyze_confirm.py` validates raw and applies the frozen gain rule.
- Result: `NO_GO_CONFIRM`. Cold-prefill paired gains +73.181%, +74.758%, +75.237%; median +74.758%. Protected cold/warm decode-duration medians −9.363%/−6.201%, below the −5% floor. First-final-content medians +68.049% cold, +2.951% warm.
- Limits: synthetic two-turn workload; three pairs; page cache uncontrolled. M3 partial, M4 not met, default unchanged. Historical FAILs unchanged. Next: source/telemetry diagnosis of decode regression under a new identity, then diverse M3 session gate if justified.
