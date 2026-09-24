# Mixed-residency Stage B result

Date: 2026-09-24  
Campaign: `results/mixed-residency-stage-b-20260924T125101Z`  
Base commit and clean tree: `086d234651596ed1e0bb492a2e7e5daf19d36596`  
Protocol: `research/MIXED-RESIDENCY-STAGE-B-PROTOCOL-20260924.md`  
Result classification: **INCONCLUSIVE_BUILD_PROVENANCE_AND_HISTOGRAM_AUTHORITY**

## Objective and evidence

The historical campaign measured the frozen h=0..4 direct CPU/GPU execution
cases for real layer-0
gpt-oss-20b MXFP4 experts 0..3, then arithmetically weight their measured
medians by the admitted Stage A grouped residency histogram. The historical campaign recorded model/host/runtime checks, but review found
that the runner did not fail closed on the llama.cpp source pin and did not bind
the prebuilt executable to the frozen Tesy source tree. In addition, the Stage A
histogram authority has since been withdrawn because its replay was phase
ambiguous. Therefore the h=0..4 measurements below are preserved as historical
isolated measurements, while campaign-level admission and all trace-weighted
claims are withdrawn. The pinned llama.cpp commit was
`4e416ee7308dd6b581796f1a6241276cd5982691`.

The live executable SHA-256 was
`c679162dc549f38ed039aa6a01bd21c1bd7e0926e3ac1e43cf3814b924621605`;
the mapped `libggml-cuda` SHA-256 was
`9534c103f6bf4c161d4fd14adc08e54d141ea57fc931e22ccba0ff0f1801d96c`.
The grouped histogram SHA-256 was
`ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

### Measured isolated cases

| GPU hits | CPU misses | Median ms | p95 ms | Speedup vs h=0 | Numerical parity |
| ---: | ---: | ---: | ---: | ---: | :--- |
| 0 | 4 | 0.760742 | 1.145763 | 1.0000x | PASS |
| 1 | 3 | 0.684444 | 0.791592 | 1.1115x | PASS |
| 2 | 2 | 0.631912 | 0.690843 | 1.2039x | PASS |
| 3 | 1 | 0.654776 | 0.682492 | 1.1618x | PASS |
| 4 | 0 | 0.268824 | 0.269577 | 2.8299x | PASS |

The selected CPU weight and bias buffer types were both `CPU`. The maximum
reported output difference from the h=0 reference was `3.57627869e-7`;
the result's numerical parity checks passed. This is numerical parity for the
isolated synthetic 0.25-mixture operator, not token equality or full-model
exactness.

### Historical trace-derived arithmetic diagnostic — NOT ADMITTED

Using the now-withdrawn historical counts h=0..4 of `[39, 26, 62, 128, 105]`, the historical weighted
median-case cost is **0.551891 ms**, equivalent to **1.378427x** versus the
measured h=0 median. This is an arithmetic weighting of separately measured
components; it is not a measured full-model speedup or physical transfer rate.

### Resource and campaign gates

The runner recorded 10 valid GPU samples and zero failed samples. Peak sampled
GPU memory used was 154 MiB, maximum GPU temperature 55 C, maximum GPU power
15.38 W, and peak process swap zero. The campaign has no `failure.json`.
Source files are `summary.json`, `trace-weighted.json`,
`resource-summary.json`, `runtime-provenance.json`, `model.json`, and
`doctor.json` under the campaign root.

## Decision, alternatives, and limits

The serial mixed cases retain measured headroom: h=2 is 1.204x and h=3 is
1.162x faster than h=0. h=3 is slower than h=2, so more GPU hits did not give
monotonic latency in this run.

A post-run audit of the exact campaign base commit `086d234` confirmed that
the binary already used the frozen CPU-backend extra/repack-aware selector:
it queried CPU extra buffers, required CPU-device support for MXFP4
`MUL_MAT_ID` at compact expert counts 1..4, and only then fell back to CPU
default. The raw result selected `CPU` for both weight and bias buffers.

That post-run source audit remains descriptive, but the campaign is not admitted under the current provenance contract. A new Stage B campaign identity is required after a provenance-preserved phase-aware histogram replay. CPU/GPU overlap is not authorized by this historical weighted result. Prediction
and prefetch remain untested.

This one 21-sample-per-case microbenchmark does not establish run-to-run
stability, concurrent scheduling benefit, full-model latency, cache behavior,
expert byte traffic, or performance per committed token. Weights were resident
before timing. The Stage A histogram assumes ideal timely insertion. No claim
of physical NVMe/RAM/VRAM traffic follows.

## Tests, failures, and next gate

Before the campaign, the focused contract tests passed (5), the pinned CUDA
build passed, and the full pytest suite passed (155). An earlier overlapping
pytest/CMake run had one transient scratch-file race; the isolated suite run
passed, as recorded in `MIXED-RESIDENCY-STAGE-B-CONTRACT-FIX-20260924.md`.
The campaign itself exited zero with all required gates PASS.

Next gate: freeze and measure CPU/GPU overlap for the material mixed cases,
without changing the numerical contract. Preserve this serial Stage B campaign as historical evidence only; it is not an admitted baseline.
