# C128 — slots40 nominal153 server screen

**Result: `SCREEN_GO_SLOTS40_NOMINAL153`.** Two new alternating pairs of
C75 waves ON, slots32 versus slots40, completed under the frozen E18/zero
swap policy and the C120 per-arm 60 s inventory/launch gate. Same original
binary and mapped libraries were used. The only config difference was
`--moe-stream-cache 32s` versus `40s`. This is a comparison of two numeric
profiles because slot count changes pool residency and prefill wave geometry.

| Metric | Pair 1 gain | Pair 2 gain | Median paired gain |
|---|---:|---:|---:|
| Warm decode, 47 tokens | 21.538% | 22.925% | **22.232%** |
| Warm first final | 19.113% | 17.414% | **18.264%** |
| Warm prefill | 17.342% | 12.279% | 14.810% |
| Cold decode | 19.535% | 8.961% | 14.248% |
| Cold first final | 10.926% | 7.303% | 9.115% |
| Cold prefill, ~2K | 7.879% | 6.759% | 7.319% |

The control warm decode durations were 13.098/13.239 s; slots40 took
10.277/10.204 s. Warm first final went from 26.063/25.388 s to
21.081/20.967 s. All four arms produced the same two messages, identical
official prompt token arrays and output counts, 2043/2197 prompt IDs,
2044 reused plus153 newly evaluated IDs in the second request, and78/47
completion tokens. The frozen answer validator, stream completion, launch
identity, resource and inventory gates passed. No arm swapped or stopped.

The paired start CPU/GPU/NVMe deltas (candidate minus control) were
[-1.875,-2,+7] °C and [-0.125,-1,-1] °C. The operational start contract
did not require narrow thermal matching, and page cache/external activity
were not experimentally controlled. The two pairs support a screen, not
confirmation or a claim that extra cache hits alone caused the improvement.
C127 provides 189+32 numeric boundary and 36 resident FFN references for
slots40; independent attention/KV/full-context fidelity is still `NOT_RUN`.

The candidate's observed warm first-final median was ~21.024 s and decode
rate ~4.59 tok/s, still short of M4's <=10 s and >=6 tok/s targets. Cold
~2K prefill does not certify cold512. C100 `NO_GO_CONFIRM` and C117
`FAIL_RESOURCES_OR_EVIDENCE` remain preserved. M3 diverse/active sustained
session, holdout8 and slots40 quality12 are not established by this screen.

Protocol/source/freeze commit: `05f9d18b0b5e99dfb1cf067c2d71c9cb1e27055e`;
raw paths/hashes are in `results/c128-slots40-nominal153-20260929T1710Z/manifest.json`.
The analyzer `tools/c128_slots40_analyze.py` revalidates the strong per-arm
inventory at actual launch time, original answer gate, equal work and all
protected metrics. The C128 epoch checkpoint charges 8499.578 s overall
conservatively, leaving at least 20300.422 s physical and 28856.007 s wall
at its timestamp. The two-hour qualification reserve remains intact.

Next: three fresh paired confirmation runs under the same operational
contract, followed by slots40 quality and diverse/active session
qualification if confirmation passes. No default or remote publication.
