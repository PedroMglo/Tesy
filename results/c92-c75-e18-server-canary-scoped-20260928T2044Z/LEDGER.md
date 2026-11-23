# C92 scoped C75 server canary

- Freeze `cca90b9aa6fb934290f6e8ec4ab6759b6603b3dc`; launched once with `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- python3 tools/c92_c75_server_canary.py run results/c92-c75-e18-server-canary-scoped-20260928T2044Z --measurement-commit cca90b9aa6fb934290f6e8ec4ab6759b6603b3dc`.
- One synthetic request completed: 71 prompt tokens, 1 completion token, finish reason `length`; 23.589 s whole process and 18.435 s request. Output is intentionally incomplete and not a quality result.
- Receipt gate passed: 8 mapped backend libraries match frozen hashes, zero workload swap/OOM/stop, cgroup peak 13,047,279,616 B, GPU total 5710 MiB, CPU 75.875 °C, GPU 49 °C, NVMe 44.85 °C. Server and GPU memory returned to idle afterward.
- Scope: load/short-forward resource admission only. C91 launcher FAIL and C78 resource FAIL preserved. 8K OFF/ON numeric boundary and session bridge remain NOT_RUN.
- Next: freeze the C80-style 8K numeric OFF/ON boundary under the admitted envelope; no performance claim from this one-token canary.
