# C25c tokenizer diagnostic

- C24 failed the official +128 ID relation before generation. C25/C25b launcher SHAs were rejected before idle/model; their prelaunch FAILs remain preserved.
- Same synthetic inputs, original model/backend/effective P12 E18 server profile and guards. This unit records official token IDs before the frozen relation gate; no generation is permitted on the expected failure.
- New preflight `READY_FOR_IDLE_ADMISSION`; focused model-free tests 12 PASS. C15 source-only; default unchanged.
- `c25c-token-diagnostic`: idle PASS 378.525 s; official counts 2035/2164, delta +129, ordered common prefix 2026. Raw server relation FAIL expected and preserved; no completion requests. Diagnostic PASS only. Pre-request maxima CPU/GPU/NVMe 50.125/42/39.85 C, GPU total 5694 MiB, swap/OOM zero. Next fixture prospectively uses 127 appended words and still requires exact +128 IDs.
