# C42 8K boundary

- New identity after C41b monitor failure; the C41b FAIL stays preserved. Same model/backend/workload/profile/guards; C42 only changes CPU sysfs telemetry to log one bounded high-value reread.
- `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c42_boundary.py results/c42-8k-boundary-20260928T0741Z --run --measurement-commit c65c1b9d609f9630c1a85a90906055513046cd3e` PASS_BOUNDARY_RETRIEVAL. Official prompt 7936 IDs, cap 256, completion 85, total 8021, exact answer Q7M2N9, finish `stop`, zero cache reuse.
- Request wall 1094.156 s; prefill 1065.079 s (7.451 tok/s); decode 29.052 s (2.926 tok/s); first final content 1092.627 s. One synthetic run, no comparative speedup claim.
- CPU max 95.25 C with 598 warning samples, cooling state zero, high/zero frequency rereads zero. GPU max 63 C / 5752 MiB; NVMe max 54.85 C; cgroup peak 13088030720 B, swap/OOM zero. Own GPU allocation and port closed.
- Physical budget including idle and C39 charge: 45992.387/57600 s. C41/C41b failures unchanged. M3 partial: 8K boundary passed, synthetic 72-minute prefix session already passed, but true assistant-history sustained usage and latency goals remain open. M4 NOT_RUN. Next C43 bounded C15 critical-path diagnostic; C15 full-model remains NOT_RUN at this checkpoint.
