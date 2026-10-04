# B2 preparation — one CPU layer, shared native wave groups

**SOURCE_AUDITED / REPRODUZIDO_MODEL_FREE**, not a physical B2 result. Existing C163/C164 primary journals demonstrate reload redundancy with deliberately optimistic wait bounds; they remain slots44/C-API traces, not slots40 server timing. The selected C127 CPU operator inputs are original disjoint32/32/29 tiles (positions0,128,160); they do not represent an entire153-token prefill.

Selected expert unions: CPU0 has66/50/55 experts by tile, union79; CPU12 has42/33/39, union64; CPU24 has52/39/43, union68. Sum of each cold tile's unique counts is171/114/134, **not observed loads**: native residency can already avoid some. The prototype must measure reservations and actual logical loads, rather than call this difference a gain.

The proposed boundary shares one native wave plan across the three tile inputs, retaining the original numerical32/32/29 MMID shapes. Native pool40, wave capacity18, four original workers and original direct load path. Each resident expert group serves all three tiles before the next wave may reuse slots; no next-layer or next-token router prediction. Gate/down/up registration order matches original model creation. Biases remain resident. Ordered routing pair weights and reduction occur after per-pair masked wave accumulation, matching C75 source.

The same code builds the original three separate wave groups as control. Source includes C211 consumer witness outside timing, expert+slot+generation+keep/readiness validation, exact original bytes and per-tile canonical/native output comparisons. CPU0/12/24 are deterministic selected layers. All references/timing remain **NOT_RUN** pending A1 discriminant and resource/numeric admission.

Model-free graph test verifies the dependency of the next wave on all three previous tile consumers. Removing two consumers is rejected. Initial fixture12slots/8experts violated the manager's real slots<experts assertion; its failed receipt is preserved. Repaired fixture12slots/16experts passed without tensor arithmetic, native I/O or target weights. This is no hardware speedup, numerical qualification or claim that merely changing loop order removes loads.

The isolated prototype has its own source/build identity and uses original qualified C75 libraries. Full Transformer/profile/default untouched. Further numeric/timing protocol will freeze before physical execution. LOCAL_ONLY.
