# C29 two-turn 8K bridge

- C28 two-turn run completed, first assistant reply exact, official prompt common2035, cache_n2036. C28 remains FAIL because its upper bound used only the original prompt. `server-context.cpp` stores generated tokens in slot.prompt.tokens before matching the next input.
- New C29 identity with the same model/backend/effective P12 profile, text, frozen assistant response, 8K context and E18 zero-swap guards. The prospective bound is cache_n between common−32 and min(second prompt IDs, first prompt IDs + first completion tokens), with cache_n + prompt_n = second prompt IDs. Unit tests include C28 as positive and impossible/unaccounted mutants as negatives (16 focused tests PASS).
- Fresh preflight `READY_FOR_IDLE_ADMISSION`: CPU48.625, GPU44, NVMe38.85 C on AC/performance. One synthetic two-turn bridge only; C15 source-only, default unchanged.
