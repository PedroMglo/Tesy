# Routed-layer exactness contract repair

Date: 2026-09-24

Base commit: `aed5f168952b0420febb225a25ef4b079a3dce55`.
Base tree: `e125828a91dea0bea520862c6395ea3d294d7ad9`.

Evidence class: `REPRODUCED_MODEL_FREE`; native build and physical campaign
were `NOT_RUN` at the base identity.

## Objective

Clear an implementation defect in the correctness-only routed-layer gate
without changing its authority, workload, thresholds, inputs or decision
scope.

## Failure and repair

The focused model-free gate failed
`test_routed_exactness_path_has_no_timing_or_prefetch_policy`. Its lexical
contract scans the `opt.routed_exactness` block for timing-policy terms. The
claim-boundary text contained `prefetch` and `cache`, even though no such
mechanism was implemented in that path.

The repair changes only that claim-boundary text. It now describes the
placement as a controlled slot-prefix partition with no dynamic placement
policy, and continues to exclude timing, full-model performance and physical
traffic claims. Native execution, exactness comparisons, routing inputs,
thresholds and the campaign runner are unchanged.

## Evidence

- Focused shell syntax, Ruff, compileall and pytest: PASS, 48 tests.
- Full Ruff, compileall, shell syntax and pytest: PASS, 219 tests.
- `git diff --check`: PASS.

## Decision and limitations

Commit the repair as a successor identity before the native build and physical
campaign. The build provenance must bind to that new commit. This record does
not provide native compilation, physical-host or routed-layer exactness
evidence.

Next discriminating gate: stack the repaired commit, verify inputs and host,
then build and run the frozen correctness-only campaign once.
