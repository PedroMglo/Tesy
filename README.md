# Tesy Scale Lab

Independent, bounded local-inference laboratory with its own Git history and pinned stock/streaming backends. Model weights and builds stay out of Git. Campaign 3 is on the dedicated review branch `campaign/c3-layer-reference-prefill-20260926-1800utc`; no merge or PR is part of this campaign.

**Current C3 result:** a one-layer-at-a-time canonical GPT-OSS 120B reference matched the streamed MoE boundary bitwise at 504 frozen layer/state/case comparisons on the laptop's actual CPU/GPU placement. Direct encoded-byte checks, slot-generation witnesses, negative/fault tests and 14 full-logit callback OFF/ON comparisons support a limited `ENGINEERING_UNBLOCKED_IN_TESTED_SCOPE` gate; attention/KV and arbitrary inputs remain outside that reference. Enabling existing next-wave preload reduced paired 496/1522-token prefill medians by **17.515/18.240%**, below the 25% goal. It completed a 20-request sustained service run at **3.291 tok/s** (late half 3.259), below 4 tok/s, while short first text/final still took 37.219/73.223 s. A selected stock20B output-cap follow-up resolved one of C2's two truncations, leaving task advantage policy dependent. See the [C3 final evidence](research/C3-FINAL-20260927.md), [R3 boundary gate](research/C3-R3-GATE-20260926.md), [paired prefill](research/C3-P2-AB-RESULT-20260926.md), [sustained service](research/C3-P2-SUSTAINED-RESULT-20260926.md), [latency](research/C3-P2-LATENCY-RESULT-20260926.md) and [selected utility follow-up](research/C3-Q-RESULT-20260926.md). The C2 historical global `CORRECTNESS_BLOCKED` state is preserved.

Campaign 2's evidence remains on its earlier branch. Its [frozen protocol](research/C2-PROTOCOL-20260926.md) and [C2-A gate result](research/C2-A-RESULT-20260926.md) govern C2 claims. The old [campaign-summary](results/campaign-summary.json) is a preserved early snapshot, as explained by the [evidence index](results/INDEX.md); it does not describe the present target state.

**Campaign 2 measured outcome:** the verified GPT-OSS 120B MXFP4 GGUF ran above available RAM with exact-demand expert streaming under an 18 GiB host cgroup and zero swap. Its 32-slot run completed 20 fixed requests in 35m56s, with 4588 tokens / 1379.108 s of backend decode = **3.327 tokens/s**, and 3.290 tokens/s in its second half. This passes its frozen >=2 sustained timing/resource gate but remains below the additional 4 tok/s objective. The historical C2 global state remains **CORRECTNESS_BLOCKED** for robust use because its full-model plain references did not complete. Short-prompt first text/final content took 42.309/74.506 s on a frozen 113-token input, missing the 10/20 s usability goals. In a frozen twelve-task synthetic pilot, target 120B passed 12/12 versus stock 20B 10/12, but required 11.478× summed request time. This supports a selective fallback hypothesis under the fixed cap, not broad default use. Physical NVMe traffic remains unattributed exclusively.

- [Current state and budget](LAB_STATE.md)
- [Documentary reporting system](docs/research-reports/README.md) — frozen R00/C1/C2 reports and evidence verifier; the [C3 reporting boundary](docs/research-reports/CURRENT-LAB.md) identifies what the newer lab campaign has and has not entered into the PDFs.
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

For the conservative tested 32-slot localhost profile, run `python3 tools/c2_launch_target.py --run-id NEW_UNIQUE_RUN_ID` from this directory on the verified physical laptop. The C3 preload opt-in is `python3 tools/c3_launch_preload.py --run-id NEW_UNIQUE_RUN_ID`. Both check the full GGUF hash outside timing and monitor resources. Stop only the owned server with `python3 tools/c2_stop_server.py NEW_UNIQUE_RUN_ID --model-path /home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf`. These commands require the existing model and pinned builds and never download weights. Raw logs, samples, float32 logit rows, weights and builds remain local; compact manifests and decisions are in Git.
