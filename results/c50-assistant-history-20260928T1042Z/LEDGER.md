# C50 actual assistant-history bridge

- C49 idle-only admission blocked at <=50 C CPU; no C49 model process.
- New prospective idle admission <=55/55/50 C CPU/GPU/NVMe, 300 contiguous seconds. All execution guards, backend, model, inputs and generation policy unchanged.
- OFF/ON speedup, 60-minute assistant-history session and M4 remain NOT_RUN.

- Idle admission PASS; both requests completed. First 2043 IDs/77 output, 299.508 s; second 2197 IDs/51 output, 40.094 s; both final content `48327`.
- Frozen prefix gate FAIL: old input LCP 2043, server cache_n 2044. Source shows slot retains generated tokens, so the gate excluded a legitimate class of matches. C50 remains FAIL; C51 needs a prospective source-backed rule.
