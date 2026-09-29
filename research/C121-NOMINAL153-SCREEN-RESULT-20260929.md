# C121 — admitted operational nominal153 screen

**Decision:** `SCREEN_GO_OPERATIONAL_NOMINAL153` for the frozen two-pair screen. The result does not confirm general promotion, replace C100 `NO_GO_CONFIRM`, or satisfy M4. C117 remains `FAIL_RESOURCES_OR_EVIDENCE`; none of its arms was counted here.

The measurement commit was `3abc0071d26d87f5ea8cabca19b2d7c3ae388f60`. Four fresh processes ran in control, candidate, candidate, control order, with a separate valid 60 s start inventory and Popen-time freshness check for each. The model, template, P12/8192/medium profile, E18 cap and nominal153 input were frozen under `results/c121-nominal153-20260929T1350Z/`. The control used C35 `c3759bad92c0e6f71bb936afea9b0a162fb83f76`; the candidate used C75 `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5` with waves ON. No usual service or default was changed.

All four receipts passed the protocol. Every first request used 2043 prompt IDs and produced 78 tokens; every second request used 2197 prompt IDs, of which 2044 were cached and 153 newly evaluated, and produced 47 tokens. All answers had the same content hash `891b37049297633347693518fe3ee5e50bf62b6be57e6ac1f0b9e8604bb223d4` and natural `stop`. This checks the observed responses, not full-logit parity of free server generation. The relevant same-profile numerical boundary is C93–C95/C111 in its tested scope.

| Pair | Warm first final, control → candidate | Warm decode, control → candidate | Cold prefill, control → candidate |
|---|---:|---:|---:|
| 1 | 39.084 → 25.244 s | 13.128 → 13.272 s | 277.877 → 68.182 s |
| 2 | 39.459 → 26.128 s | 13.311 → 14.131 s | 276.884 → 68.968 s |

Median paired gains: warm first final **34.597%**, warm prefill **53.091%**, cold first final **69.263%**, cold prefill **75.277%**, cold decode **+1.369%**, warm decode **−3.629%**. Both warm first-final pairs were positive. All four protected median metrics cleared the frozen −5% floor; the second warm decode pair alone was −6.161%, which remains visible in `timing-pairs.json`. The candidate's observed median warm first final was 25.686 s, and median warm decode throughput was 3.434 tok/s. Thus the screen supports a useful prefill/session-latency improvement in this workload, while decode and M4 remain open.

The start regime was operational warm, without narrow temperature matching. Pair 1 candidate-minus-control starts were +3.75/+2/+8 °C CPU/GPU/NVMe; pair 2 were +2.375/+2/+2 °C. Alternating order and guards do not remove environmental confounding. CPU peaks of 95.125 °C were warnings below the 100 °C stop; GPU peaks were at most 65 °C, NVMe at most 57.85 °C, VRAM total at most 5758 MiB, cgroup at most 13,098,582,016 B, workload swap zero. No thermal failure is inferred. Raw SHA256 and per-arm receipts are in `manifest.json`; raw remains local.

`decision.json`, `timing-pairs.json` and `manifest.json` were generated only after all four arms and the strong inventory/launch chain passed. The original C120 premodel SHA failure remains preserved separately. Next discriminator: a phase-marked nominal153 decode capture, with source-defined boundaries and neutral instrumentation, to identify whether expert read/copy/wait or compute dominates. C52b's M3 scope remains unchanged; M4 is not demonstrated. Publication remains local only.
