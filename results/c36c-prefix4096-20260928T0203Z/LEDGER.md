# C36c 4096-ID prefix bridge

- New identity after C36b official token count delta129 rejected its predicted delta128 before any chat request. This fixture uses 127 beta words to target 128 IDs; 4096-prefix hypothesis, cache threshold and E18 guards unchanged. Physical run NOT_RUN.
- `c36c-prefix4096-bridge` (`08ede32`): PASS, 4035/4163 official IDs (delta128), LCP4026, cache_n0/4026. Request 545.982/37.667 s; second first final 37.432 s, decode 4.025 tok/s. CPU/GPU/NVMe max 95.125/62/52.85 C, GPU5752 MiB, swap/OOM0. Scope: one synthetic same-user extension; M3 partial, M4 NOT_RUN.
