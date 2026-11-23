# C7c P8 probe bridge result

Objective: same-host numerical bridge from the unmodified C4 prefill probe to the new C7 parametrized P8 probe. Measurement commit `5e01697b2c7cb1602c07790bb3525866d397daa4`, tree `365521bf9cfc04d3796e15e2141b9913497919e3`. Both E18 runs, raw manifests and complete logits SHA are in `results/c7c-20260927T1224Z/bridge-summary.json`.

The full 201088-F32 prefill logits vectors match bitwise for the 113 frozen IDs. Both runs completed without swap, OOM, resource guard or mapped-library mismatch, using CPU0–28/GPU29–35 plus output GPU. The alternative of an effective-option/build difference affecting this P8 output was rejected for this short prefill. The bridge does not compare performance and cannot establish equality across toolchains or longer workloads.

A second transient read-only `nvidia-smi` query failed just after the C4 process exited; four following queries and a fresh C7 preflight passed, with no matching NVIDIA/Xid kernel event. The raw incident is preserved and the watchdog remained fail-closed in each run. Decision: P8 bridge PASS within scope. Paired timing, server, context and utility: NOT_RUN. Next gate: two alternating fresh-process 113+32 teacher-forced pairs, followed by medium screening if integrity/resources hold.
