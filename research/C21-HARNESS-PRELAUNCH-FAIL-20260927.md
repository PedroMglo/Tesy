# C21 prelaunch harness failure

- Objective/base: new exact-prefix OFF/ON paired screen, frozen at `63bddc0daeba61964c6cc1e98afc9cde5843700b`. Alternative explanation from C20 was thermal matching; C21 used the prospective cool-start band.
- Evidence: `c21-p1-off` 300.066 s idle PASS, 601 samples, CPU/GPU/NVMe below 50/50/45 C and cadence <=1 s. The server gate rejected `output_root` because `results/c21-prefix-pairs-20260927T1927Z/raw/` was absent. The check occurs before server launch in `tools/c2_server_run.py`; model runs zero. Source logs and idle raw are preserved in the C21 root.
- Decision: `FAIL_HARNESS_PRELAUNCH`; all C21 timings and other arms NOT_RUN. This is neither a thermal failure nor a model/correctness result. No old FAIL is relabelled. C15 stays source-only; M3 partial; M4 NOT_RUN.
- Repair: require the raw output directory at freeze and preflight, with a model-free negative test for missing root. Use a fresh C22 root and fresh OFF/ON controls. Preserve C21's failed identity.
