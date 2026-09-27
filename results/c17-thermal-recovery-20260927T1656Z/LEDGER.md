# C17 ledger

- New identity after C16 pre-model idle cadence block. Reused the read-only historical audit, preserved all four old 513 thermal FAILs and C16 block.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c17_idle_window tools.test_c5_compare tools.test_c2_gate tools.test_c3_approval tools.test_c3_terminal_sample tools.test_c9_server_admission tools.test_c9_prefix_normalize`: 50 PASS. Eight protocols and exact C9/C11 command/profile differences checked model-free; full model hash and fresh E18 scope preflight PASS.
- Physical C17 arms: NOT_RUN at freeze. Next: T0 P8 init after a complete fresh idle window. C15 remains source-only; default unchanged.
