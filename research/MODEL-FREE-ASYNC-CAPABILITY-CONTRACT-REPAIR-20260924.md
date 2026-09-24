# Model-free async-capability contract repair — 2026-09-24

## Objective

Repair a stale full-suite textual contract while preserving the already
implemented requirement that an async live-handoff timing candidate needs a
GPU backend that advertises async capability.

## Base and evidence class

Base commit: `dbb362082eb3b1a4e7f8417185ae6519d9132187`  
Evidence: `REPRODUCED_SOURCE_CONTRACT_FAILURE / IMPLEMENTATION_NOT_RUN /
PHYSICAL_NOT_RUN`.

The full model-free suite failed only
`test_async_candidate_requires_gpu_async_capability`. The test required the
old single-mode spelling `opt.async_overlap && !gpu_props.caps.async`.

## Diagnosis and decision

The implementation gets GPU properties and fail-closes when either
`opt.async_overlap` **or** `opt.live_handoff_timing` is requested without
`gpu_props.caps.async`. This is a stronger, relevant guard: live-handoff
timing contains the async candidate and must not run on a backend lacking the
advertised capability.

The contract now asserts the two-mode guard and its failure condition. Native
execution, the timing protocol, thresholds, routing, samples, scheduling, and
claim scope are unchanged.

## Alternatives, limitations, and next gate

Changing the native guard back to the old single-mode expression would remove
the live-timing capability check. Weakening the test to only search for the
failure message would not protect either mode. Neither alternative was chosen.

No native rebuild or physical campaign has run for this repair. Re-run the
full model-free gate from the repaired commit; only a PASS permits the native
rebuild and a fresh physical campaign identity.
