# C26 prospective streaming bridge

- C25c measured C24 text pair at 2035/2164 IDs: delta +129, common 2026, no generation. C26 freezes 127 inserted words before outputs; the official tokenizer must confirm exactly +128 IDs and >=1900 common IDs before sending two SSE requests.
- Same original model/backend/effective P12 ngl12 ub32 slots32 preload ON 8K full-SWA server, E18 zero swap, CPU100 and other guards; synthetic growing prompt, medium effort, cap256. Completion-fenced first text/final-content and cache are measured. No full M3/M4 claim.
- New preflight `READY_FOR_IDLE_ADMISSION`; focused model-free tests 12 PASS. C15 source-only, default unchanged.
