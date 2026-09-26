# Tesy Scale Lab

Independent, bounded local-inference laboratory with its own Git history and pinned stock/streaming backends. Model weights and builds stay out of Git. Campaign 3 is currently on local-only branch `campaign/c3-layer-reference-prefill-20260926-1800utc`; it has not been pushed or merged.

**Current C3 result:** a one-layer-at-a-time canonical GPT-OSS 120B reference matched the streamed MoE boundary bitwise at 504 frozen layer/state/case comparisons on the laptop's actual CPU/GPU placement. Direct encoded-byte checks, slot-generation witnesses, negative/fault tests and 14 full-logit callback OFF/ON comparisons support a limited `ENGINEERING_UNBLOCKED_IN_TESTED_SCOPE` gate. This is conditional on captured upstream activations; it is not a full plain-model or daily-use certificate. Prefill optimization and new utility tests have not yet produced C3 results. See the [C3 R3 gate](research/C3-R3-GATE-20260926.md), [broad reference](research/C3-R2-BROAD-RESULT-20260926.md) and [lifetime/negative result](research/C3-R2-LIFETIME-RESULT-20260926.md).

Campaign 2's evidence remains on its earlier branch. Its [frozen protocol](research/C2-PROTOCOL-20260926.md) and [C2-A gate result](research/C2-A-RESULT-20260926.md) govern C2 claims. The old [campaign-summary](results/campaign-summary.json) is a preserved early snapshot, as explained by the [evidence index](results/INDEX.md); it does not describe the present target state.

**Campaign 2 measured outcome:** the verified GPT-OSS 120B MXFP4 GGUF ran above available RAM with exact-demand expert streaming under an 18 GiB host cgroup and zero swap. Its 32-slot run completed 20 fixed requests in 35m56s, with 4588 tokens / 1379.108 s of backend decode = **3.327 tokens/s**, and 3.290 tokens/s in its second half. This passes its frozen >=2 sustained timing/resource gate but remains below the additional 4 tok/s objective. The historical C2 global state remains **CORRECTNESS_BLOCKED** for robust use because its full-model plain references did not complete. Short-prompt first text/final content took 42.309/74.506 s on a frozen 113-token input, missing the 10/20 s usability goals. In a frozen twelve-task synthetic pilot, target 120B passed 12/12 versus stock 20B 10/12, but required 11.478× summed request time. This supports a selective fallback hypothesis under the fixed cap, not broad default use. Physical NVMe traffic remains unattributed exclusively.

- [Current state and budget](LAB_STATE.md)
- [C2 sustained 32-slot diagnostic](research/C2-C-RESULT-20260926.md)
- [C2 target latency](research/C2-D-RESULT-20260926.md)
- [C2 launcher and context lifecycle](research/C2-F-RESULT-20260926.md)
- [C2 twelve-task utility pilot](research/C2-E-RESULT-20260926.md)
- [C2 correctness limits](research/C2-B-RESULT-20260926.md)
- [Whole-plan audit](research/PLAN-AUDIT-20260926.md)
- [Decisions and retained failures](DECISIONS.md)
- [M4 target execution and correction scope](research/M4-RESULT-20260926.md)
- [M2 phase I/O estimate](research/M2-PHASE-IO-RESULT-20260926.md)
- [M3 cache-capacity comparisons](research/M3-RESULT-20260926.md)
- [M3 24/32-slot A/B result](research/M3-CAPACITY32-RESULT-20260926.md)
- [M5 sustained server result](research/M5-SERVER-RESULT-20260926.md)
- [M6 paired task result](research/M6-RESULT-20260926.md)
- [Publication provenance and rollback](research/ADR-PUBLICATION-20260926.md)

For the tested C2 **diagnostic** 32-slot localhost profile, run `python3 tools/c2_launch_target.py --run-id NEW_UNIQUE_RUN_ID` from this directory on the verified physical laptop. It checks the full GGUF hash outside timing, then monitors resources; stop only that server with `python3 tools/c2_stop_server.py NEW_UNIQUE_RUN_ID --model-path /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf`. The older 24-slot smoke command is `./tools/serve_target24.sh`; it belongs to campaign 1. These commands require the existing model and pinned builds and never download weights. Raw logs, samples, float32 logit rows, model weights and builds remain local; compact manifests and decisions are committed locally. C2 is not remotely published under its current instruction.
