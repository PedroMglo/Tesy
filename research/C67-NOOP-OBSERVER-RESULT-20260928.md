# C67 no-op observer result

- Objective/base: separate callback registration from C60 capture work in the C66 layer25 invalid-ID abort. Tesy measurement `ac5f911e973821570e40fa38be22f3fe49f458b3`; same isolated backend `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22` and P12 numeric profile.
- Evidence class: `MEDIDO_NO_TARGET` one bounded no-op observer arm. It completed and its 33 full logits vectors were bitwise equal to the C66 plain control. Mapped libraries, raw hashes and resources are in `results/c67-noop-observer-20260928T1628Z/`.
- Interpretation: callback registration with `false` and no tensor read did not reproduce the error in this arm. The C66 capture work is associated with its failure. A timing-sensitive graph/backend race remains an alternative; this is not causal proof of a faulty `tensor_get`.
- C48, C61 and C66 failures remain. No ON-arm wave fidelity, canonical reference, wave timing, session utility or M4 claim follows.
- Next discriminant: inspect scheduler callback semantics and isolate `ask=true` selection from tensor reads with a model-free graph before another full-model wave experiment; pivot if no safe boundary emerges.
