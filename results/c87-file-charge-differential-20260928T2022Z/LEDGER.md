# C87 file charge differential

- Freeze: `8f2cdcab8340c1ad4ae0dd7dc628cb5658b412ec`; `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c87_file_charge_analysis` passed 3/3.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c87_file_charge_analysis.py` read only the hash-verified C76b/C78 records; no model run.
- At matched 14 s, C78 minus C76b cgroup charge was +2,502,569,984 B, of which `memory.file` was +2,498,019,328 B; `anon` was −12,288 B and RSS +208,896 B. C78 remains a resource FAIL.
- Unknown: charged inode, reclaimability, and why the file charge differed. The incomplete C78 capture yields no numeric PASS.
- Next gate: preserve obsolete local build outputs on NVMe, check whether this materially raises host headroom, then perform a new capacity preflight if justified.
