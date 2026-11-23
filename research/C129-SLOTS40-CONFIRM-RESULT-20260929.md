# C129 — slots40 nominal153 confirmation

**Decision: `CONFIRMED_SLOTS40_NOMINAL153` for the frozen two-turn
assistant-history workload.** Three fresh alternating pairs compared the
same C75 waves-ON backend at 32 versus 40 expert slots per layer. All six
processes completed under E18/zero swap, with unique strong 60 s start
inventories bound to actual Popen, valid model/library identity, answer,
prefix and resource receipts. No usual service or default changed.

| Metric | Median paired gain, slots40 versus slots32 |
|---|---:|
| Warm decode, 47 tokens | **23.173%** |
| Warm first final | 18.009% |
| Warm prefill | 13.331% |
| Cold decode | 23.900% |
| Cold first final, ~2K | 11.074% |
| Cold prefill, ~2K | 9.251% |

The three warm decode gains were 29.881%, 23.173%, and 22.896%, all
positive. The predeclared confirmation median threshold was 8%, with each
protected timing median above −5%; every protection passed. In the six
arms, warm decode took 13.204–14.529 s at slots32 and 10.181–10.195 s at
slots40. Warm first-final was 25.122–27.518 s versus 20.755–20.779 s.
Each pair had identical official prompt token arrays, assistant messages,
completion counts, 2044 reused/153 new prompt IDs and 47 output tokens on
the incremental request. Resource peaks and start temperatures per arm are
in `timing-pairs.json`; the operational start regime did not impose narrow
thermal matching or a controlled page cache.

This confirms useful performance for **this new profile and workload**,
not the pure causal effect of residency. Slot count changes prefill wave
geometry as well as primary expert pool capacity, and the trace has not
partitioned their contributions. It also does not mean M4: candidate warm
first-final is still ~20.76 s versus <=10 s and decode is ~4.61 tok/s
versus >=6. The first request has ~2043 IDs, not cold512. M3 diverse
conversation and active sustained load, slots40 quality12, holdout8,
7936-token boundary and independent full attention/KV remain open. C100
`NO_GO_CONFIRM` and C117 `FAIL_RESOURCES_OR_EVIDENCE` remain unchanged.

Source/freeze/measurement commit:
`03fb94d74e54e410c92725bfdcdba43c54064aed`. The compact raw hashes
are in `results/c129-slots40-confirm-20260929T1735Z/manifest.json`; raw is
local. `tools/c129_slots40_analyze.py` revalidates all arms and the frozen
decision gate. At the result checkpoint the epoch is conservatively charged
9703.441 s physical, leaving >=19096.559 s and 27085.198 s wall.

Next: qualify slots40 against the original 12-task quality suite and a
prospectively frozen eight-task holdout; then test diverse real assistant
history and sustained active session on this confirmed profile. No remote
publication is authorized.
