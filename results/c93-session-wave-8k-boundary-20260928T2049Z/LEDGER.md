# C93 8K numeric OFF/ON boundary

- Source `29404e8356390ac991150f5050b2bbb9133c17f0`, directed stat fix `f7e10acb6af25fea6f2f4d97907e5bec98ab2897`, measurement `a891cfb2183e3c1a6c3fe4c9bdf43edc2f9eb9da`. C70/C72 tests 2/2 and C93 freeze tests 2/2 passed. The initial model-free freeze failed on an extra `ctime_ns` field; corrected before any physical run.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c93_session_wave_8k_boundary.py run results/c93-session-wave-8k-boundary-20260928T2049Z --measurement-commit a891cfb2183e3c1a6c3fe4c9bdf43edc2f9eb9da --arm off` passed, then the same command with `--arm on` passed.
- OFF/ON: 250 numeric states, 2 masked, 1500 active core stages plus masks and 5 full logits bitwise equal; 996 byte/lifetime witnesses each. ON observed 80,800 parked sentinels. E18/zero swap valid; cgroup peak 15.510/13.563 GB, GPU total peak 5786 MiB both.
- The 62.068/44.865 s capture times are instrumented and page cache uncontrolled; no speedup claim. Resident canonical reference, fresh ON repeat, server reuse/timing and M4 remain NOT_RUN.
- Historical C48, C78 and C91 FAILs unchanged. Next: 8K same-build resident FFN reference, then fresh ON repeat.
