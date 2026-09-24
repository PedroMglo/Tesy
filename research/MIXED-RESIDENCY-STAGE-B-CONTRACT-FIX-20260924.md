# Stage B claim-boundary contract fix

Date: 2026-09-24  
Branch: `research/mixed-residency-stage-b-20260924`  
Base commit: `4b9da04` (clean worktree before edit)  
Evidence class: source-contract correction; Stage B measurement NOT_RUN at this record

## Objective and decision

Make the raw result's claim boundary state `no expert-weight transfer` as the
frozen source-contract test requires. The prior C++ source said `no expert `
then `weight transfer` in adjacent literals. The emitted sentence conveyed the
same scope, but the expected phrase was absent from the source and output.

The chosen change updates only this claim-boundary sentence. The alternative
was to loosen the test to accept the prior wording; that would not make the
machine-readable result use the explicit frozen phrase. No timing path,
workload, threshold, baseline, model identity, or parity rule changed.

## Verification and failures

- Focused source-contract test: 5 passed.
- Pinned CUDA mixed-residency binary build: PASS.
- Full pytest after build completion: 155 passed.
- An earlier full pytest run during CMake configuration had 154 passed and one
  `FileNotFoundError`: the repository-boundary scan read a temporary CMake
  scratch file while CMake removed it. The isolated rerun passed. This was a
  test/build race, not a Stage B result.
- Frozen grouped histogram SHA-256: `ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.

## Limits and next gate

No performance conclusion follows from this correction. The next gate is the
prospective Stage B runner in `research/MIXED-RESIDENCY-STAGE-B-PROTOCOL-20260924.md`
with a new output root and a clean committed worktree. Preserve any failed
campaign root and report its failure rather than reusing it.
