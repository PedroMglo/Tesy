# C127 — slots40 numeric and short forward result

**Decision: `PASS_SLOTS40_NUMERIC_AND_SHORT_FORWARD_ADMISSION`.** C75 P12 with
40 expert slots per layer completed a frozen 189+32 capture at context8192.
OFF and ON had bitwise equal active routed states and five full logits in the
captured boundary. The 36 independent resident FFN recomputations of the ON
activations passed 250 active rows and two masked rows. This is a new numeric
profile: 40 slots change both residency and 32-token ubatch wave geometry.

The OFF process took 49.804 s and ON 35.228 s, but this single short
numeric probe has uncontrolled page cache and is **not** a performance
screen. The original C75/slots32 confirmed server remains the useful
operational comparator. C100 `NO_GO_CONFIRM` and C117
`FAIL_RESOURCES_OR_EVIDENCE` remain unchanged.

Both capture processes completed with E18 and workload swap zero. OFF peak
cgroup was 17,162,174,464 bytes and GPU use 6,894 MiB; ON peak cgroup was
16,126,992,384 bytes and GPU use 6,900 MiB. The current GPU total-use guard
was 7,676 MiB. The probe demonstrates allocation and short forward at this
shape, not sustained nominal153, full 8K context, or independent attention/KV
fidelity. No service or default changed.

Source/freeze/capture/reference/analysis commits are recorded by full SHA in
`protocol.json`, `capture-stage.json`, `reference-summary.json`, and
`decision.json`. Compact hashes and raw tree digests are in `manifest.json`;
raw remains local under `raw/`. `tools/c127_analyze_numeric.py` revalidates
the chain. The C127 physical charge is a conservative 660 s envelope from
the inventory interval through reference completion, with 155.453 s of
measured model process time. The epoch checkpoint leaves at least
21,141.521 s of physical budget and the wall limit is tracked separately.

Next discriminant: fresh, prospectively frozen two-pair C75 ON slots32 versus
slots40 server screen on the nominal153 actual assistant-history fixture,
with the same E18 cap and strong per-arm inventory. A timing benefit is not
inferred from numeric admission. Holdout8, diverse active sustained session,
full 8K boundary on this profile and M4 remain `NOT_RUN`/`NOT_DEMONSTRATED`.
