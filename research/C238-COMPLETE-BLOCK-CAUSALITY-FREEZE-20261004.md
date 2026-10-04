# C238 — prospective complete fixed-B causal diagnostic

SOURCE_AUDITED: B2/4 use native CUDA MMVQ; B8 crosses the Ada MXFP4
MMVQ maximum7 into MMQ. This is explicit cross-shape arithmetic, not an
implicit claim of R0 equality. ubatch32 and all other C75/P12/slots40 settings
remain fixed. All B logits flags are true. Actual last FFN and vocabulary
projection row counts must equal B in the callback before accepting a run.

REPRODUZIDO_MODEL_FREE: five directed acceptance/budget tests pass, covering
all-accept bonus, every rejection position, rollback accounting, EOS/cap,
missing rows and invalid metrics. An initial unittest invocation failed to
import the tools modules; discovery with the actual import path passes.
The prior native rebuild bridge passed, with its original failure preserved.

Protocol: B2, B4, B8 in that order, fresh model process per shape, fixed189
official prefix, native R0-generated inputs recorded before comparisons.
For each shape, change a future input at every possible non-anchor position
and require all preceding complete logit vectors bitwise identical. Resubmit
the clean complete grid after each rejected suffix; require bitwise equality
despite changed expert residency. Every recorded phase retains selected
consumer expert/slot/generation/bytes witnesses with C211 direct reads.
No unverified token is published. The native R0 sequence is not retokenized.

This is diagnostic, not the amortization screen. Its success alone does not
qualify an independent draft-free R1 evaluator or new-shape canonical FFNs.
Real EOS/context-edge/cancellation coverage and development classes remain
explicit next gates. No EAGLE weights are downloaded.

Prospective cap16.75GiB, same for all shapes, derived policy STREAMING/swap0.
C237 peak15960801280B plus805306368B observer/workspace uncertainty stays
below preventive17448304640B. These are estimates; actual admission and
telemetry remain authoritative. Own60s inventory per process,240s process
deadline,45s postgate,1080s whole family,768MiB projected raw. On the first
negative or invalid run, preserve it and mark remaining shapes NOT_RUN.
No replacement run under this identity. Source repairs require new identity.

Full immutable settings/hashes and budget admission are in
`results/c238-complete-block-causality-20261004/protocol.json`.
Measurement HEAD is recorded by the supervisor after this freeze commit.
LOCAL_ONLY; original service/default/presets are untouched.
