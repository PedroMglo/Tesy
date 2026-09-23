# B0/B1 stock placement diagnostic

Campaign: `results/b0-b1-20260923T212353Z`

Classification: `MEASURED_STOCK_B0_B1_DIAGNOSTIC`.

| Run | Arm | TTFT ms | Prompt tok/s | Decode tok/s | Peak VRAM MiB | Peak RSS GiB | Swap MiB | Temp °C |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1-b0 | B0 | 532.22 | 290.69 | 50.714 | 6859.0 | 11.78 | 0.0 | 56.0 |
| 2-b1 | B1 | 882.87 | 175.03 | 34.623 | 1717.0 | 11.78 | 0.0 | 57.0 |
| 3-b1 | B1 | 886.08 | 174.35 | 34.851 | 1717.0 | 11.42 | 0.0 | 59.0 |
| 4-b0 | B0 | 547.43 | 282.63 | 51.512 | 6859.0 | 11.78 | 0.0 | 59.0 |

## Claim boundary

No performance winner was preregistered for this diagnostic.
B0 and B1 are both stock llama.cpp configurations.
These results do not measure physical NVMe or PCIe expert traffic and do not demonstrate a Tesy speedup, native cache benefit, speculation benefit or >RAM execution.

Raw logs/resource samples remain outside Git; `manifest.json` contains their byte sizes and SHA-256 identities.
