# C94: full 8K resident routed FFN reference

- **Objective/base:** rule out shared streamed errors after C93 OFF/ON equality. Source `7555fd7444cc89d1ff1052d7ab524ce811bfcb7f`; witness measurement `4054e5cc766d591c28348d4b309b68cf60f58cd4`; remaining measurement `20fb9b11517d33cf78d1cce1eb6af856e5054ec0`.
- **Evidence:** same C75 pin and actual layer device; all 36 independently loaded resident FFNs recomputed routing from C93 8K captured activations. Ordered IDs, routing weights and FFN outputs were bitwise for 250 numeric rows; two masked last-layer rows remained N/A. Six moved/boundary witnesses passed before the remaining 30. **MEDIDO_NO_TARGET**, isolated FFN only.
- **Resources:** E16 cap, zero workload swap/stop; maximum cgroup peak 4,133,711,872 B, GPU 1734 MiB, CPU 61.375 °C across 36 separate processes. Sum bounded elapsed 65.432 s is reference cost, not serving latency.
- **Alternative/limit:** a race across fresh wave-ON processes is still possible, and independent attention/KV correctness is not covered. Server exact-prefix behavior, timing, quality and M4 are **NOT_RUN**.
- **Decision:** preserve full resident FFN PASS within frozen 8K scope and all historical FAILs. Next discriminant is a new-ID fresh ON capture compared bitwise to C93 ON, then server timing if it passes.
