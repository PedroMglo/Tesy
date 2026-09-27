# C10b init-only result

- Objective/base: bounded original-backend P8 native ub64 8K server admission, measurement commit `8093999a871bf8c210298b79f1bb32fc0ff979c0` (tree frozen). Evidence class: physical init-only resource measurement; raw `results/c10b-20260927T1520Z/raw/c10b-g1-init.*` stays local.
- Run: `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- python3 tools/c10b_ub64_server.py results/c10b-20260927T1520Z --run init --measurement-commit 8093999a871bf8c210298b79f1bb32fc0ff979c0`. Return 0, monitor/identity/raw hashes validated, five telemetry samples, no guard/event/swap failure.
- Observed: elapsed 4.602 s; peak RSS 4.816 GB, cgroup 5.321 GB, GPU total 3884 MiB, CPU 53.375 C, GPU 46 C, NVMe 40.85 C. Start CPU 49.25 C satisfied the frozen ≤55 C precondition.
- Decision: `CAPACITY_ADMITTED_INIT_ONLY`. No forward, logits, numerical parity, timing, prefix reuse, 8K utilization or quality claim. Next discriminating gate: the frozen four-token minimum forward, one new physical scope after this result commit. Default unchanged.
