# C59 placement accounting

- Objective: determine whether moving two more layers to CUDA (P14/slots32/ub32) is worth a bounded capacity screen, and whether P16/slots32 is statically admissible.
- Base: C7 687-tensor GGUF inventory, rehashed against its accounting; unchanged P12 C52b 20-request session and C58 canary GPU peaks; C58 hardware-derived VRAM stop. Backend C35 remains the proposed placement control.
- Evidence class: TENSOR_ACCOUNTING_PLUS_MEASURED_P12_PEAK, not P14/P16 execution or timing.
- Hypothesis: two extra GPU layers may reduce CPU expert demand and improve workload latency. Alternative: CUDA compute, transfers, routing change or workspace may offset the saved CPU work. Placement is a new numerical profile, not a bitwise P12 variant.
- Input/accounting: 13,219,200 B per expert, 32 slots = 423,014,400 B per layer, plus 34,155,008 B nonstream layer tensors. P12 uses 11 GPU layers; P14 13; P16 15. The larger observed P12 GPU peak is 5752 MiB and the prospective GPU total stop is 7676 MiB.
- Static decision: P14 adds 871.98 MiB of known pools/dense, giving 6623.98 MiB before new workspace, 1052.02 MiB to stop. P16 gives 7495.96 MiB, just 180.04 MiB to stop before new workspace. Admit neither from this arithmetic alone; P14 qualifies for bounded init and short forward, P16 needs a stronger workspace bound or earlier measured P14 headroom.
- Correctness/performance gate for P14: freeze separate numeric profile, verify placement and artifact bytes, same-profile reference/logits, then two alternate screen pairs with no cross-profile equality requirement. No P14 speedup is claimed by C59.
- Next: C57 numeric boundary on the wave repair and P14 bounded capacity under the same physical policy, one model at a time. The better evidence determines which mechanism gets confirmation resources.
