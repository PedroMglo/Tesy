# C26 prospective streaming bridge

- C25c measured C24 text pair at 2035/2164 IDs: delta +129, common 2026, no generation. C26 freezes 127 inserted words before outputs; the official tokenizer must confirm exactly +128 IDs and >=1900 common IDs before sending two SSE requests.
- Same original model/backend/effective P12 ngl12 ub32 slots32 preload ON 8K full-SWA server, E18 zero swap, CPU100 and other guards; synthetic growing prompt, medium effort, cap256. Completion-fenced first text/final-content and cache are measured. No full M3/M4 claim.
- New preflight `READY_FOR_IDLE_ADMISSION`; focused model-free tests 12 PASS. C15 source-only, default unchanged.
- `c26-g1-prefix2048`: idle PASS 300.060 s; official IDs 2035/2163, exact +128 and 2026 common. The first streaming request stopped on the server's initial `content:null` role event because the client parser required a string. Zero completed responses; no TTFT/session claim. CPU/GPU/NVMe maxima 95.125/63/47.85 C; GPU total 5746 MiB, swap/OOM zero. Preserve this harness FAIL, repair parser using server-task.cpp source and a discriminating null-event test, then start C27.
