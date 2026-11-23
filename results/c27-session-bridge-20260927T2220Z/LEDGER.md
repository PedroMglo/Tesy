# C27 8K streaming bridge

- C26 passed exact 2035/2163 official IDs but its first SSE request stopped on an initial `content:null` event. C26 FAIL preserved; C27 is new identity with only the tested client parser repair. Original model/backend/effective P12 profile, text, output cap and guards remain the same.
- Preflight `READY_FOR_IDLE_ADMISSION` on AC/performance, CPU 47.25 C, GPU 44 C, NVMe 38.85 C. Focused parser/tests 13 PASS. Two requests require complete `[DONE]`, usage, timings, finite resources and exact prefix cache range.
- This synthetic growing prompt is a bridge, not true conversation or M3/M4 qualification. C15 source-only; default unchanged.
- `c27-g1-prefix2048` PASS: 2035/2163 official prompt IDs, exact 2026 reused on request 2; complete SSE `[DONE]`/usage/timings. Cold request 289.676 s (prompt 274.379 s, decode 3.401 tok/s); incremental 37.858 s (prompt 22.801 s, first text 23.402 s, first final content 37.643 s, decode 4.054 tok/s). CPU max95.125 C warning, GPU62 C, NVMe54.85 C, GPU total5752 MiB, swap/OOM zero. The M4 targets 10 s first final and 6 tok/s are not met. Next: true two-turn/session bridge and bottleneck assessment; no default change.
