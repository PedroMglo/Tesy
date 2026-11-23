# Mixed-residency async overlap result

Date: 2026-09-24

Protocol: `research/MIXED-RESIDENCY-ASYNC-OVERLAP-PROTOCOL-20260924.md`.

Frozen measurement Tesy commit: `3500fd4dadeac6303091577ea3a275328810feac`.

Frozen measurement tree: `fe9c63df533759b22f740d1ca6cca374efc3722c`.

Pinned llama.cpp commit: `4e416ee7308dd6b581796f1a6241276cd5982691`.

Successful campaign: `research/results/mixed-residency-async-overlap-20260924T152625Z/`.

## Objective and evidence class

Measure same-campaign serial and post-D2H CPU/GPU async timings for the isolated real-weight routed FFN at layer 0, with frozen h=0..4 expert placement cases and the admitted trace-derived histogram. The case timings are **measured** on the physical reference laptop. The histogram-weighted value is an **arithmetic diagnostic** from measured case medians, not full-model latency.

The predecessor candidate at `768ccfd2a2f9e7b3da2ff61a3006c7d5e17f6e08` failed the final model-free Ruff gate (`I001` extra blank line). No physical campaign was run on that HEAD. Its failure record is `research/ASYNC-FINAL-HEAD-MODEL-FREE-GATE-20260924.md`. The prospective replacement commit changed only that blank line and passed the required gates before this campaign.

## Gates and provenance

- Focused model-free: Ruff, Python compileall, shell syntax, and 26 pytest tests PASS.
- Complete model-free: Ruff, Python compileall, shell syntax, and 188 pytest tests PASS.
- Model SHA-256: `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`; size 12,109,564,352 bytes.
- Admitted histogram SHA-256: `ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.
- Doctor reference check PASS; virtualization PHYSICAL; RTX 4060 Laptop GPU free of compute processes before execution.
- Native CUDA build provenance PASS; executable SHA-256 `fa0ec961ae1e6870d10f3f0d3232c4fb2b12ba76268301ed7efcb9bfdbbd1a98`; mapped `libggml-cuda` SHA-256 `9534c103f6bf4c161d4fd14adc08e54d141ea57fc931e22ccba0ff0f1801d96c`.
- Runtime executable, argv, mapped CUDA library, Python path, and clean source identities PASS. No `failure.json` exists in the successful campaign root.

## Result

| GPU hits | Serial median, ms | Async median, ms | Async p95, ms | Numerical parity |
| ---: | ---: | ---: | ---: | :--- |
| 0 | 0.707528 | serial anchor | — | PASS |
| 1 | 0.627646 | 0.572496 | 0.653557 | PASS |
| 2 | 0.535837 | 0.444647 | 2.174731 | PASS |
| 3 | 0.568572 | 0.440819 | 2.115844 | PASS |
| 4 | 0.269436 | serial anchor | — | PASS |

All cases used 21 timed samples after 3 warmups, with 5 inner repetitions. h=0 and h=4 are serial anchors in both weighted arms. The async cases passed the frozen finite-output, normalized-error and cosine thresholds against the all-CPU reference. The maximum absolute errors are nonzero, so this establishes **numerical parity of the isolated operator**, not bitwise equality or token equality.

The trace-weighted same-campaign serial median diagnostic is **0.4950063228 ms**. The async candidate diagnostic is **0.4298951194 ms**, a **13.1536% reduction** or **1.15146x speedup**. The preregistered 10% implementation gate required at most **0.4455056905 ms**. The persisted decision is `ASYNC_OVERLAP_MEASURED_GO`.

Resource sampling recorded 13 valid GPU samples, zero failed samples, zero peak process swap, 53 C maximum GPU temperature, 21.33 W maximum GPU power, and 176,160,768 bytes peak GPU memory used. The runner's headroom and provenance gates passed.

## Alternatives, failures, limitations, and next gate

The frozen alternatives were to retain the async mechanism for a narrower integration experiment if the 10% median gate passed, or return to the serial path if it did not. The observed result selects the first alternative under that predeclared rule. The failed predecessor lint gate remains recorded and is not relabelled as a successful campaign.

The h=2 and h=3 async p95 values exceed 2 ms despite favorable medians. This campaign has one physical run; it does not establish run-to-run stability, tail-latency benefit, full-model speedup, cache behavior, physical PCIe/DRAM/NVMe traffic, or bytes per exact committed token. The synthetic routing input is not a committed-token trace. Prediction, prefetch, cache policy and speculation remain **NOT_RUN**.

The next discriminating gate is a separate prospective protocol for the smallest routed-layer/backend integration, preserving exact routing and a stock/serial comparator. It should include a tail-latency acceptance criterion and resource/provenance telemetry before physical execution. No prefetch work is authorized by this isolated result alone.
