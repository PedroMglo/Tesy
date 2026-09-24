# Mixed-residency async steady-tail result

Date: 2026-09-24

Protocol: `MIXED-RESIDENCY-ASYNC-TAIL-ORDER-PROTOCOL-20260924.md`.

Measurement commit: `df022f16458350c4b99ffc0155362bba1df7d15b`.
Measurement tree: `45fba4a1c927d3bac44d327678dff91166a30b4b`.
Campaign: `results/mixed-residency-async-tail-order-20260924T160204Z/`.

## Objective and evidence class

Measure order-conditioned median and p95 latency of the isolated real-weight
mixed-residency FFN on the physical reference laptop. The timings below are
measured. The histogram-weighted median is an arithmetic diagnostic, not a
full-model measurement. Routing remains synthetic and frozen.

## Gates and provenance

- The initial focused gate at `f34e2f0` stopped at Ruff I001. An import-order
  repair in a test file was committed before this campaign; it did not change
  native code, measurement policy, thresholds or inputs.
- Focused model-free: shell syntax, Ruff, compileall and 35 tests PASS.
- Full model-free: Ruff, compileall, shell syntax and 197 tests PASS.
- Model SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`;
  size 12,109,564,352 bytes.
- Histogram SHA-256 `ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.
- llama.cpp commit `4e416ee7308dd6b581796f1a6241276cd5982691`;
  worktree clean.
- Doctor reference check PASS, virtualization PHYSICAL, RTX 4060 Laptop GPU,
  no competing GPU compute process before execution.
- Native build provenance PASS at measurement commit. Executable SHA-256
  `fa0ec961ae1e6870d10f3f0d3232c4fb2b12ba76268301ed7efcb9bfdbbd1a98`.
  Runtime executable, argv and mapped CUDA library provenance PASS.
- The raw sample count and schedule match 81 pairs and
  `even_serial_async_odd_async_serial`; all numerical parity checks passed.
- Resource telemetry: 28/28 valid GPU samples, zero failed samples, zero
  process swap, 61 C maximum GPU temperature, 49.27 W maximum GPU power.
  No `failure.json` exists.

## Result

| GPU hits | AA/SS median | AA/SS p95 | SA/AA p95 | Both gates |
| ---: | ---: | ---: | ---: | :--- |
| 2 | 0.867938 | 0.895385 | 1.049133 | PASS |
| 3 | 0.709154 | 0.763401 | 0.958248 | PASS |

Each steady bucket contains 40 observations. The prospective limits are
AA/SS median at most 0.90 and AA/SS p95 at most 1.10 for both h=2 and h=3.
The recorded decision is `ASYNC_STEADY_TAIL_GO`.

The same-campaign trace-weighted isolated median diagnostic is 0.4749016494
ms serial and 0.4039171672 ms async, a 14.9472% reduction. Its independent
decision is `ASYNC_OVERLAP_MEASURED_GO`.

The prior 21-sample campaign's ~3x serial-to-async transition amplification
did not recur at h=2 or h=3 in this campaign. This is a measured difference
between two runs, not an explanation of the earlier spikes or evidence of
run-to-run stability.

## Alternatives, decision, failures and limitations

The predeclared alternatives were to stop async overlap on a valid
`ASYNC_STEADY_TAIL_NO_GO`, or advance to a separately gated routed-layer
integration on `ASYNC_STEADY_TAIL_GO`. The latter applies. No failure occurred
in this campaign. The earlier lint failure remains a failed gate on its own
commit, not a successful measurement.

This result establishes numerical parity and order-conditioned latency only
for the isolated operator. It does not establish exact routed-layer behavior,
bitwise equality, committed-token equality, full-model speed, cache/prefetch
benefit, physical PCIe/DRAM/NVMe traffic, bytes per committed token, or
run-to-run stability.

Next discriminating gate: prospectively define and implement the minimum
routed-layer integration, preserving the model's exact router choices and a
same-layer serial comparator, then validate exactness before timing.
