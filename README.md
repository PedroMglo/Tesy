# Tesy Scale Lab

Independent, bounded local-inference laboratory published on the `scale-lab` branch of the Tesy Git remote. This branch has its own Git history and is not a change to Tesy's `main` tree or PR stack. It pins a stock `llama.cpp` backend and one expert-streaming candidate, and keeps model weights and builds out of Git.

Campaign 2 is in progress on a **local-only** `campaign/c2-correctness-usability-20260926-1349utc` branch. Its [frozen protocol](research/C2-PROTOCOL-20260926.md) and [C2-A gate result](research/C2-A-RESULT-20260926.md) take precedence for new claims. The old [campaign-summary](results/campaign-summary.json) is a preserved early snapshot, as explained by the [evidence index](results/INDEX.md); it does not describe the present target state.

**Measured outcome:** the verified GPT-OSS 120B MXFP4 GGUF ran above available RAM with exact-demand expert streaming under an 18 GiB host cgroup and zero swap. A prospectively frozen 24-slot localhost-server run completed ten requests in 22m22s at 2.733 backend decode tokens/s aggregated across 839 s of decode. A later three-pair 24/32-slot A/B reached 3.269 mean decode tokens/s over bounded two-request runs with 32 slots; that configuration has no sustained validation. The 120B and stock 20B each passed 8/10 held-out tasks; no task advantage was observed. Numerical parity is limited to a short fixed prefix, and physical NVMe traffic is not exclusively attributed.

- [Current state and budget](LAB_STATE.md)
- [Whole-plan audit](research/PLAN-AUDIT-20260926.md)
- [Decisions and retained failures](DECISIONS.md)
- [M4 target execution and correction scope](research/M4-RESULT-20260926.md)
- [M2 phase I/O estimate](research/M2-PHASE-IO-RESULT-20260926.md)
- [M3 cache-capacity comparisons](research/M3-RESULT-20260926.md)
- [M3 24/32-slot A/B result](research/M3-CAPACITY32-RESULT-20260926.md)
- [M5 sustained server result](research/M5-SERVER-RESULT-20260926.md)
- [M6 paired task result](research/M6-RESULT-20260926.md)
- [Publication provenance and rollback](research/ADR-PUBLICATION-20260926.md)

To start the smoke-tested localhost server on the specified physical laptop, run `./tools/serve_target24.sh`. For a monitored replay of the task suite, run `./tools/run_task_eval.sh target120b NEW_UNIQUE_RUN_ID eval`. These commands require the verified local GGUF and the pinned backend build at the paths recorded in their scripts; they never download weights. Raw logs, one-second samples, float32 logit rows, model weights and build outputs remain local under the frozen publication policy. The compact manifests under `results/` preserve commands, identities, stop reasons, metrics and hashes.
