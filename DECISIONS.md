# Decisions and A/B ledger

| Time (Europe/Lisbon) | Hypothesis/change | Result | Decision and reason |
|---|---|---|---|
| 2026-09-26 00:44 | Use a sibling lab at the requested path | Path absent and outside authorized writable roots | Create a separate nested Git repo inside the authorized Tesy root; do not alter its branch or tracked files. |
| 2026-09-26 00:49 | Use stock llama.cpp and one expert streaming branch | Immutable SHAs resolved and cloned; no run yet | Keep stock independent and compare the candidate with streaming off/on before a practical cross-version comparison. |
| 2026-09-26 00:50 | Configure CUDA with default GCC 16 | CMake compiler identification failed: CUDA 13.3 rejects GCC >15 | Use installed GCC 15 for both backends; no system toolchain changes. |
| 2026-09-26 00:52 | Stream 120B native safetensors directly through candidate | Source accepts GGUF model loader and GGUF offsets | Incompatible artifact format for this candidate. Do not convert or download automatically. |

No A/B performance result exists yet. Failures remain in the ledger.
