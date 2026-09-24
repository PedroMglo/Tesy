# Mixed-residency overlap-bound result

Date: 2026-09-24

Protocol: `research/MIXED-RESIDENCY-OVERLAP-BOUND-PROTOCOL-20260924.md`

Frozen Tesy commit: `ca4100e755cea2e0261e4a550af1c9681b64b4e4`

Frozen Tesy tree: `83917e86dc20fa5e5e8115901de9c5206ca5aef1`

Pinned llama.cpp commit: `4e416ee7308dd6b581796f1a6241276cd5982691`

Successful campaign: `research/results/mixed-residency-overlap-bound-20260924T135006Z/`

Preserved failed attempt: `research/results/mixed-residency-overlap-bound-20260924T134933Z/`

## Objective and evidence class

Measure the serial direct wall time and separate components of the real-weight
layer-0 mixed-residency FFN for GPU-hit cases h=0..4. Apply the frozen Stage A
grouped histogram to the specified post-D2H CPU/GPU compute-overlap formula.
The direct and component timings are **measured**. The weighted overlap value
is a **derived diagnostic**, not measured concurrent execution.

The campaign verified the locked 12,109,564,352-byte gpt-oss-20b MXFP4 GGUF
with SHA-256
`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.
The admitted grouped histogram SHA-256 was
`ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.
The successful run recorded clean Tesy and llama.cpp trees, reference-host
identity PASS, exact executable/argv/CUDA-library provenance PASS, and CPU
weight and bias buffer types `CPU`. The executable SHA-256 was
`99182ab2c5fabfac999f1a920b735965c5c1ff3bf5786e6c58cbc489268fe791`;
the mapped CUDA-library SHA-256 was
`9534c103f6bf4c161d4fd14adc08e54d141ea57fc931e22ccba0ff0f1801d96c`.

## Result

| GPU hits | Direct median, ms | Post-D2H bound, ms | Dominating compute branch | Numerical parity |
| ---: | ---: | ---: | :--- | :--- |
| 0 | 0.748496 | 0.748496 | CPU only | PASS |
| 1 | 0.698970 | 0.505055 | CPU | PASS |
| 2 | 0.576852 | 0.400702 | CPU | PASS |
| 3 | 0.583072 | 0.390497 | GPU | PASS |
| 4 | 0.269220 | 0.269220 | GPU only | PASS |

For h=0 and h=4 the bound equals the measured direct-wall median exactly:
there is no CPU/GPU compute overlap to apply. All five isolated cases passed
the frozen numerical parity thresholds; this is not token equality.

The histogram-weighted direct diagnostic was **0.516752 ms**. The weighted
post-D2H overlap bound was **0.403939 ms**, or 1.279283x relative to the
weighted direct diagnostic. The prospectively frozen 10% gate required the
bound to be at most **0.465077 ms**. The persisted decision is therefore
`OVERLAP_IMPLEMENTATION_GO`.

The runner recorded 12 valid GPU resource samples, zero failed GPU samples,
zero peak process swap, 54 C maximum GPU temperature, 20.92 W maximum GPU
power, 161,480,704 bytes peak GPU memory used, and all frozen RAM/VRAM
headroom gates PASS. The successful root has no `failure.json`.

## Failure preserved and tests

The first campaign root, `...T134933Z`, ended at `model_verify`: `/usr/bin/python3`
could not import the editable `tesy` package. Its `failure.json` classifies
`FAIL_CAMPAIGN_STAGE`; it has no performance conclusion. The successful
campaign used the already installed project virtual environment by prepending
`$PWD/.venv/bin` to `PATH` and a new output root. No threshold, workload,
model, or calculation changed between attempts.

Before the successful run, `bash -n`, Python `compileall`, Ruff, and the two
focused pytest modules passed (11 tests). The pinned native CUDA build passed.
The full repository test suite was **NOT_RUN** in this phase.

## Alternatives, decision, and limitations

The frozen alternatives were to implement the narrow post-D2H CPU/GPU compute
overlap if the bound met the 10% gate, or stop at the simpler serial path if it
did not. The observed diagnostic meets the gate, so implementation of that
specific concurrent path is justified for an experiment. Prediction and
prefetch remain **NOT_RUN** and are not justified by this result alone.

Component medians were measured separately and need not add to direct-wall
medians. The histogram assumes timely ideal residency. This single campaign
does not establish a real async speedup, full-model latency, cache behavior,
physical PCIe/DRAM/NVMe traffic, or bytes per exact committed token. It does
not establish run-to-run stability. The next discriminating gate is a frozen
concurrent-versus-serial measurement with the same numerical contract and
complete provenance/resource telemetry, prepared on a dedicated branch before
any physical execution.
