# B0/B1 stock placement diagnostic

Campaign: `results/b0-b1-20260923T212353Z`

Classification: `INCONCLUSIVE_STOCK_B0_B1_DIAGNOSTIC`.

| Run | Arm | TTFT ms | Prompt tok/s | Decode tok/s | Peak VRAM MiB | Peak RSS GiB | Swap MiB | Temp °C |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1-b0 | B0 | 532.22 | 290.69 | 50.714 | 6859.0 | 11.78 | 0.0 | 56.0 |
| 2-b1 | B1 | 882.87 | 175.03 | 34.623 | 1717.0 | 11.78 | 0.0 | 57.0 |
| 3-b1 | B1 | 886.08 | 174.35 | 34.851 | 1717.0 | 11.42 | 0.0 | 59.0 |
| 4-b0 | B0 | 547.43 | 282.63 | 51.512 | 6859.0 | 11.78 | 0.0 | 59.0 |

## Review invalidation

This campaign is retained but is **not admitted as a same-work B0/B1 placement
comparison** for three independent reasons discovered in review:

1. all four required `placement.txt` files are empty, so the realized stock
   placement was not verified;
2. the campaign did not preserve the full CUDA/compiler/dynamically loaded
   backend identity required by the prospective protocol;
3. generated token IDs were not retained, so B0/B1 trajectory equality was not
   established.

The timing and resource numbers above remain descriptive observations only.
They may motivate a new experiment, but they are not an admitted performance
comparison and must not be used to claim a B0/B1 winner.

A new campaign identity with the hardened runner is required.

## Validation status

Campaign-local validation beyond the four recorded executions: `NOT_RUN`.

No model-free/unit/shell/manifest validation result was captured as part of this
campaign identity, so none is retroactively claimed here. Repository CI on the
publication branch is a separate code/publication check and does not repair or
upgrade the evidentiary status of this preserved campaign.

## Claim boundary

No performance winner was preregistered for this diagnostic.
B0 and B1 are both stock llama.cpp configurations.
These results do not measure physical NVMe or PCIe expert traffic and do not demonstrate a Tesy speedup, native cache benefit, speculation benefit or >RAM execution.

Raw logs/resource samples remain outside Git; `manifest.json` contains their byte sizes and SHA-256 identities.
