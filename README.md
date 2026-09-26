# Tesy Scale Lab

Independent, bounded local-inference laboratory published on the `scale-lab` branch of the Tesy Git remote. This branch has its own Git history and is not a change to Tesy's `main` tree or PR stack. It pins a stock `llama.cpp` backend and one expert-streaming candidate, and keeps model weights and builds out of Git.

Campaign 2 is in progress on a **local-only** `campaign/c2-correctness-usability-20260926-1349utc` branch. Its [frozen protocol](research/C2-PROTOCOL-20260926.md) and [C2-A gate result](research/C2-A-RESULT-20260926.md) take precedence for new claims. The old [campaign-summary](results/campaign-summary.json) is a preserved early snapshot, as explained by the [evidence index](results/INDEX.md); it does not describe the present target state.

**Current measured outcome:** the verified GPT-OSS 120B MXFP4 GGUF ran above available RAM with exact-demand expert streaming under an 18 GiB host cgroup and zero swap. Campaign 2's new 32-slot run completed 20 fixed requests in 35m56s, with 4588 tokens / 1379.108 s of backend decode = **3.327 tokens/s**, and 3.290 tokens/s in its second half. This passes its frozen >=2 sustained timing/resource gate but remains below the additional 4 tok/s objective. It is a performance diagnostic: independent target numerical coverage beyond the old four-token prefix is blocked by two bounded reference attempts. Short-prompt first text/final content took 42.309/74.506 s on a frozen 113-token input, missing the 10/20 s usability goals. The earlier 120B and stock 20B each passed 8/10 tasks; a new twelve-task comparison is in progress and has no result yet. Physical NVMe traffic remains unattributed exclusively.

- [Current state and budget](LAB_STATE.md)
- [C2 sustained 32-slot diagnostic](research/C2-C-RESULT-20260926.md)
- [C2 target latency](research/C2-D-RESULT-20260926.md)
- [C2 launcher and context lifecycle](research/C2-F-RESULT-20260926.md)
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
