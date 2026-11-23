# C41b 8K boundary

- New identity after C41 prelaunch SHA-argument failure; same workload, backend, model, numerical profile and guards. Full measurement commit required. C41 stays failed without model.
- `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c41b_boundary.py results/c41b-8k-boundary-20260928T0723Z --run --measurement-commit cc226d1a0a030227aba817f062023811aaec940d` stopped at 784.785 s. Official tokenizer returned 7936 IDs. The monitor rejected `policy19` first frequency 21786195 kHz. No response completed; status `FAIL_RESOURCES_OR_EVIDENCE`, not thermal failure or 8K capacity result.
- Last valid sample at 778.200 s: CPU max 95.125 C (warning), GPU max 63 C, NVMe max 45.85 C, GPU 5746 MiB, cgroup peak 13069123584 B, zero swap/OOM/cooling. Final cgroup zero swap/OOM. Own process, GPU use and port 18367 closed. C41b raw and stop reasons are preserved.
- Next: bounded one-reread repair for an impossible high `cpuinfo_avg_freq`, with explicit receipt and negative persistent-high mutant. New C41c identity and preflight; no hidden retry of C41b.
