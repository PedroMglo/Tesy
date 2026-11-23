# C105 ledger

- Measurement commit `e71af4b5e8e337b77cc176d7e6d544134956aace`; command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c105_c84_trace_boundary.py run results/c105-c84-8k-trace-boundary-20260928T2335Z --measurement-commit e71af4b5e8e337b77cc176d7e6d544134956aace`.
- One instrumented C84 P12 8K numeric 189+32 run passed same-profile bitwise comparison to hash-checked C93 ON: 250 numeric states, 2 masked, 5 logits, 996 byte witnesses. Trace validator passed 41,842 events, 12,755 demands, 6005 loads, 1357 waits, zero overflow.
- Peak cgroup 15.487 GB, GPU 5786 MiB, swap 0, no stop. Diagnostic elapsed 46.376 s is not production timing. L2 savings and physical NVMe attribution NOT_RUN. C100 NO_GO and historical FAILs unchanged. Next: bounded L2 trace simulation, then decide whether any cache prototype merits model runs.
