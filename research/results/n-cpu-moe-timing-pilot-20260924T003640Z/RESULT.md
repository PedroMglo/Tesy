# stock placement timing pilot

Capacity evidence commit: `5a8bbf08eb95069b1847f724e5d1be98c6392678`.

Classification: `MEASURED_STOCK_PLACEMENT_PILOT_DIAGNOSTIC`.

| Placement | TTFT ms | Prompt tok/s | Decode tok/s | Peak VRAM MiB | RSS GiB | Swap MiB | Temp °C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| auto-fit-frozen | 583.35 | 265.42 | 48.902 | 6546.0 | 11.78 | 0.0 | 53.0 |
| n-cpu-moe-12 | 578.07 | 267.73 | 48.909 | 6548.0 | 11.78 | 0.0 | 55.0 |
| n-cpu-moe-24 | 910.13 | 169.75 | 35.422 | 1696.0 | 11.41 | 0.0 | 56.0 |

Trajectory comparability: `PASS`; all three observations produced the same 64-token trajectory SHA-256 `c64fefef84af574bdd51ff71625016d434f958497a58748c5de78ca280ce6b42`.

Pilot placements were selected from published capacity evidence; admitted manual points there were [12, 16, 20, 24].

Realized placement telemetry: `PASS` for all three runs. CUDA0 model buffers matched the same-placement llama-fit-params projection within the frozen tolerance, and live process argv matched the exact frozen server argv.

Host `CPU_Mapped` buffer spans are retained as diagnostics and classified `NOT_COMPARABLE_MMAP_SPAN`; they are not compared with fit-print Host logical model MiB and are not resident-DRAM claims.

This is one observation per placement. It is diagnostic only: no confirmatory performance winner or Pareto frontier is claimed.

No physical PCIe/NVMe/DRAM traffic, Tesy speedup, >RAM execution or scientific novelty claim follows.
