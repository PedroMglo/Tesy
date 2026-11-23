# C79 E18 capacity check

- Fresh physical inventory: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c55_inventory.py results/c79-e18-wave-repeat-20260928T1934Z`.
- cap_max 19,058,917,376 B, E18 requested 19,327,352,832 B: short 256 MiB.
- CAPACITY_NOT_ADMITTED. No model loaded, no run ID or numeric result. C78 resource stop remains FAIL; C76b/C77 PASSs remain scoped.
- Next: source/model-free 8K session bridge, and a new capacity admission only if host headroom improves. No remote/default change.
