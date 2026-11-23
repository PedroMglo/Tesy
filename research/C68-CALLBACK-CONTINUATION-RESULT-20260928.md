# C68 observer continuation result

- Objective/base: resolve a specific observer cancellation path found after C66. Tesy measurement `5c18e428034d2cfc87d1b0aa1627947174190e84`; diagnostic backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`. The original C60/C61/C66 outputs and failures were not edited.
- Evidence: `SOURCE_AUDITED` GGML scheduler breaks a split when selected node delivery returns false; C60 did that for out-of-scope `attn_post_norm`. `REPRODUZIDO_MODEL_FREE` C68 synthetic graph gave intermediate 3 on false versus complete 5 on true. `MEDIDO_NO_TARGET` one repaired observer OFF P12 run completed with C61 layer0 capture schema and five full selected logits bitwise equal to C66 plain.
- Interpretation: this identifies a harness defect capable of causing the invalid-ID path and its repaired OFF capture passed. It does not retroactively change C61/C66, prove every source of invalid IDs absent, or validate wave ON.
- Resource/provenance: E18 zero workload swap, no OOM or guard stop; raw hashes and mapped libraries in `results/c68-callback-repair-20260928T1636Z/manifest.json` and receipt. Raw remains local.
- Alternatives/NOT_RUN: wave skip may still change active FFN bits (C48 original FAIL); canonical 36-layer comparison, ON repetition, timing and quality are NOT_RUN. Next discriminant is a new wave ON boundary against frozen C68 OFF.
