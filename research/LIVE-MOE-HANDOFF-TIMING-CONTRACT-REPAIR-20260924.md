# Live MoE handoff timing: contract-boundary repair — 2026-09-24

## Objective

Repair the model-free contract test discovered while validating the frozen
`RESIDENT_EXPERT_LIVE_HANDOFF_TIMING` gate, without changing its measured
workload, order, threshold, decision rule, model identity, or claim boundary.

## Base and evidence class

Base commit: `2349f582c2f854a23144e954db87325b017ee986`  
Base tree: `bb024952fc4c81833e864dc56c618dcd242ea52e`  
Evidence: `REPRODUCED_SOURCE_CONTRACT_FAILURE / IMPLEMENTATION_NOT_RUN /
PHYSICAL_NOT_RUN`.

The focused gate reproduced one failure in
`test_live_handoff_uses_stock_then_handoff_arms_with_rollbacks`: it expected
two occurrences of `llama_memory_seq_rm(` but counted five.

## Diagnosis

The implementation of `run_live_handoff_exactness` contains exactly two
rollbacks: one after the stock-reference arm and one after the handoff arm.
The test's terminating marker, `void print_parity(`, is after the subsequent
live-timing helper functions. Its textual slice therefore also contained the
two timing exactness-pair rollbacks and the repeated-token timing-trial
rollback. This is a test-boundary defect, not evidence of an extra exactness
rollback or an execution-semantics change.

## Alternatives and decision

Considered changing native rollback code, loosening the count, or correcting
the test slice. The native code and an exact count of two remain the intended
contract. The test now ends at the immediately following
`capture_live_timing_pair` definition, excluding timing-only functions.

No native implementation, timing samples, schedule, statistics, decision
logic, or physical campaign root was changed or created.

## Validation and limitations

The focussed failure was reproduced before this repair. Targeted and full
model-free validation, native rebuild, and physical timing remain
`NOT_RUN_AFTER_REPAIR` until executed from the repaired commit. This repair
does not constitute physical timing evidence.

## Next discriminating gate

Re-run the frozen focused and full model-free gates. If both pass, record the
new commit/tree as the prospective campaign provenance, rebuild the pinned
native dependency, and use a new campaign identity for the physical gate.
