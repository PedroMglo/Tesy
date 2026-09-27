# C9 server bridge ledger

- Hypothesis: original backend P8 native preload ON can admit an explicit 8K full-SWA single-slot server under E18, then expose exact-prefix reuse. Strong alternative: server/KV/workspace exceeds reservation or cache does not reuse the intended IDs.
- Current unit: init-only, no inference. Next if admitted: frozen minimum forward; otherwise preserve capacity failure and choose another envelope/profile.

- G1 init-only measurement commit `04c35c7b8275556d91ec5afb4c2baaac9f7e3cf1`, run `c9-g1-init`: server ready 3.703 s, elapsed 4.368 s; 4 samples, mapped backend libraries exactly frozen, clean exit, no swap/OOM/cap events. Sampled maxima RSS 5,175,140,352 B, cgroup 4,974,436,352 B, GPU total 3876 MiB; final cgroup peak 5,340,352,512 B. No inference was requested.
- Decision: CAPACITY_ADMITTED_INIT_ONLY. Pools are lazy; first-forward workspace and server numeric profile remain UNKNOWN. Next: freeze a separate minimum 8K forward under E18 and stop on any guard. Owner server/default unchanged.
