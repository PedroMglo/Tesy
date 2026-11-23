# C95: fresh-process 8K wave ON repeat

- **Objective/base:** check races after C93 OFF/ON and C94 36-layer resident FFN passes. Source `7a0989d1f8b57975355fef538428f1dabbaa00d9`; measurement `193185d1e0bb244d39c33a2780216d956406158b`.
- **Evidence:** new C80-binary/C75 process in the same P12 8K preload-ON profile produced 250 numeric states, two masked positions, 1500 active core stages, wave masks and five full logits bitwise identical to the hash-verified C93 ON capture. Both had 80,800 parked sentinels. Cgroup peak 15,899,992,064 B, GPU 5786 MiB, CPU 65.875 °C, zero swap/stop. **MEDIDO_NO_TARGET** for this frozen capture.
- **Alternative/limit:** this excludes the observed fresh-process race in the selected states, but does not independently validate attention/KV, unobserved prompts, sampling distribution, server prefix reuse or useful-answer latency. Capture elapsed is not production timing.
- **Decision:** retain C93/C94/C95 numerical coverage; do not promote performance or M4. C48/C78/C91 failures unchanged. Next gate is a contemporary C35 control/C75 candidate server bridge with exact session token and cache accounting.
