# C50 assistant-history admission revision

- **Objective:** execute the two-turn assistant-history gate whose C49 run never reached model load. This is a new campaign identity, not a continuation of C49.
- **Base:** investigation `2a5aad2`; backend `c3759bad92c0e6f71bb936afea9b0a162fb83f76`, same existing P12 server binary, model, 8K/full-SWA/KV/cache options, two-turn inputs, generation policy and E18 execution guards as C49. The protocol records exact hashes.
- **Reason for revision:** C49 spent 900.047 s on idle telemetry. CPU started at 51 °C and had sparse values just above its conservative <=50 °C band; no model or request ran. Its `THERMAL_PREFLIGHT_BLOCKED` receipt remains intact. The owner explicitly requested continuing despite temperatures not falling further.
- **Only prospective delta:** 300 contiguous idle seconds with CPU/GPU/NVMe <=55/55/50 °C. CPU >=95 °C is still a warning; CPU >=100 °C, explicit thermal limit/clock collapse, GPU >80 °C, NVMe >70 °C or any other execution guard ends the run. No power/fan policy change.
- **Hypothesis and alternative:** as in C49: actual prior assistant content enables an exact-prefix hit and a byte-for-byte repeated five-digit answer; otherwise serialization/cache behavior or generation breaks the contract.
- **Model-free evidence:** the 46 focused tests include positive and negative actual-assistant-history construction. The historical C37 user-only 20-request regime and C48 numeric FAIL are unaffected.
- **Decision:** one bounded full-model run after admission, first failure stops. PASS is only this synthetic two-turn scope; speedup causality, 60-minute assistant-history stability, general quality and M4 stay unclaimed.
