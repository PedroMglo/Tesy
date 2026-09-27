# C9 server bridge ledger

- Hypothesis: original backend P8 native preload ON can admit an explicit 8K full-SWA single-slot server under E18, then expose exact-prefix reuse. Strong alternative: server/KV/workspace exceeds reservation or cache does not reuse the intended IDs.
- Current unit: init-only, no inference. Next if admitted: frozen minimum forward; otherwise preserve capacity failure and choose another envelope/profile.

- G1 init-only measurement commit `04c35c7b8275556d91ec5afb4c2baaac9f7e3cf1`, run `c9-g1-init`: server ready 3.703 s, elapsed 4.368 s; 4 samples, mapped backend libraries exactly frozen, clean exit, no swap/OOM/cap events. Sampled maxima RSS 5,175,140,352 B, cgroup 4,974,436,352 B, GPU total 3876 MiB; final cgroup peak 5,340,352,512 B. No inference was requested.
- Decision: CAPACITY_ADMITTED_INIT_ONLY. Pools are lazy; first-forward workspace and server numeric profile remain UNKNOWN. Next: freeze a separate minimum 8K forward under E18 and stop on any guard. Owner server/default unchanged.

- Model-free forward freeze correction: protocol01 omitted C2-style server raw time from global budget; protocol02 counted it; protocol03 also rejects malformed/negative receipts and pins the budget reader. No model execution used protocol01/02. Current physical total after init is 5046.085 s. Focused 68 tests PASS. Next: `c9-g2-forward` under protocol03.

- Administrative `c9-g2-preflight-rejected01`: wrong commit SHA argument rejected before server start; raw receipt preserved and 1 s conservatively charged. No model run.
- G2 measurement commit `62c7bce79a6c8bf9e443cd4453aa1af1f99cbfd7`, run `c9-g2-forward`: 78 prompt IDs and four output tokens, zero cache reuse; backend prefill 25.634 s, decode 1.039 s, API wall 26.677 s. Normalized C2 gate, mapped libraries, raw hashes, 29 samples, exits and resource guards PASS. Sampled RSS 15,126,409,216 B, cgroup 14,912,307,200 B, GPU total 3896 MiB, swap zero.
- Decision: MINIMUM_FORWARD_ADMITTED only. Cold512, exact-prefix, 7936+256 boundary, 12-task utility and >=60 min/20 requests NOT_RUN. Next: frozen cold512/prefix screen; usual service/default unchanged.
