# C49 actual assistant-history bridge

- **Objective:** test whether the existing P12 server can keep an exact prefix when the next request contains the previous assistant's actual answer. C37 passed a 20-request, 72-minute synthetic user-only extension regime; C48's CPU parked-pair mechanism failed bitwise and is not used here.
- **Base and pin:** investigation `b276d81`; isolated C35 backend `c3759bad92c0e6f71bb936afea9b0a162fb83f76`, its existing server binary and mapped-library hashes, existing GPT-OSS 120B GGUF SHA. The C49 protocol records the tree and binary hashes. C48 FAIL remains untouched.
- **Hypothesis:** a fixed template date and compatible server options preserve at least 1900 official token IDs across a generated assistant reply, and the second response repeats the first five-digit content exactly.
- **Alternative:** real assistant-history serialization, cache policy, or generation prevents prefix reuse or answer continuity despite C37's synthetic retention.
- **Frozen test:** one E18 P12 full-SWA 8K server, medium effort, preload ON, two streaming requests. The first prompt contains 1960 `alpha` words and asks for any five-digit code. The second adds 127 `beta` words and asks to repeat the actual first answer. The harness inserts only the first API `content` as the assistant message. Output cap 256, temperature 0, seed 42, fixed template date, no retry. Cache gate is LCP >=1900 and `cache_n` within 32 IDs of LCP. Both responses need completion fence, first final content timing, and `finish_reason=stop`; second content must equal first content byte for byte.
- **Resources:** new preflight, 300 seconds of idle telemetry, E18/zero swap, CPU95 warning/100 stop, GPU80/NVMe70, GPU <=6500 MiB reservation, MemAvailable >=6 GiB. One process, no external service change.
- **Evidence class before run:** source/harness and 46 model-free tests passed. No C49 output or timing claim yet.
- **Limit:** one synthetic two-turn conversation cannot certify long-term assistant-history sessions, quality generally, speedup causality, or M4. The existing 20-request C37 regime remains user-only synthetic.

## Admission result

- Measurement commit `5e166223be6f5147d15bcff55e4693aa1736bf40`. The 900.047 s idle series had 1801 samples, maximum gap 0.914 s, and zero GPU model load. The CPU began at 51.0 °C, ended at 48.0 °C, and had isolated readings above the frozen 50 °C admission band. The last 60 s trend was +0.225 °C; the conservative contiguous admission predicate still failed.
- **THERMAL_PREFLIGHT_BLOCKED.** No model or request was run, so this is neither a runtime thermal guard failure nor a session fidelity result. M3 remains partial and M4 NOT_RUN.
- **Next:** C50 new identity with a prospective idle band of CPU/GPU/NVMe <=55/55/50 °C for 300 contiguous seconds. The CPU warning at 95 °C and stop at 100 °C, GPU/NVMe/RAM/swap guards, model, backend, workload and generation policy remain unchanged. The owner explicitly requested continuation even if the CPU does not cool further.
