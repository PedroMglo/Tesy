# C40 quality recovery

- New identity after C39 runner/watchdog interruption. Same frozen tasks and P8/P12 numerical profiles; parent-death safeguard prevents orphaned model. C38/C39 failures preserved; 2400 s unreceipted runtime charged.

- `c40-p8` PASS_COMPLETE_12_TASKS: 12/12 validator PASS, 2621.682 s, max CPU89 C/GPU55 C/NVMe56.85 C, GPU3938 MiB, zero swap/OOM. First two C38 P8 messages and usage repeated exactly.
- `c40-p12` PASS_COMPLETE_12_TASKS: 12/12 validator PASS, 2492.679 s, max CPU89 C/GPU56 C/NVMe56.85 C, GPU5752 MiB, zero swap/OOM. Measurement commit `7d9fc01cfaab7a1ddd7bb5d8765e738ae918b0ec`; P8 measurement commit `7372cab03ae8c600921650f18f6c1f0a66c360d6`.
- C38 stock20 comparator remains 11/12, with `c38-plan-01` truncated at the frozen 3072 output cap. P8/P12 each resolved 2/12 by 120 s and 12/12 by 600 s; medians to first final content were 148.26/140.10 s. One run per profile: elapsed differences are descriptive, not a confirmed timing gain.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c40_close.py` validated receipts, raw hashes and task order and wrote compact evidence. Its first model-free invocation stopped on a nullable 20B first-content timestamp after writing an identical P12 summary; the corrected invocation checked that file before closing. No physical rerun occurred.
- C38 telemetry FAIL and C39 orchestrator interruption remain FAIL. M3 remains partial; 7936+256 boundary, true assistant-history continuity and M4 are NOT_RUN. C15 full-model is NOT_RUN. Physical budget used: 43504.970/57600 s, including idle and conservative 2400 s C39 charge. Next: C41 7936+256 8K boundary under E18.
