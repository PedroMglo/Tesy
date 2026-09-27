# C17 ledger

- New identity after C16 pre-model idle cadence block. Reused the read-only historical audit, preserved all four old 513 thermal FAILs and C16 block.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c17_idle_window tools.test_c5_compare tools.test_c2_gate tools.test_c3_approval tools.test_c3_terminal_sample tools.test_c9_server_admission tools.test_c9_prefix_normalize`: 50 PASS. Eight protocols and exact C9/C11 command/profile differences checked model-free; full model hash and fresh E18 scope preflight PASS.
- Physical C17 arms: NOT_RUN at freeze. Next: T0 P8 init after a complete fresh idle window. C15 remains source-only; default unchanged.
- T0 P8 init `c17-t0-p8-init`, measurement commit `1b6757a70ce28277119a064f3daa0b33d485e887`: idle 300.051 s/601 samples, qualifying max gap0.785 s, baseline CPU41.125/GPU39/NVMe32.85 C. Init-only PASS, rc0/no stop; peak CPU50.75 C, GPU3897 MiB, cgroup6.132 GB, RSS5.547 GB, swap/OOM0. Raw SHA `423b5cc1349afaca3d6c560f5eed4f955a6892a79fd246564f0d2fcc651b295f`; GPU compute clear afterward. No forward or 513 result yet.
