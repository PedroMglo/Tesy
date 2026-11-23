# C7 G0 gate repair

Objective: repair known C6 capture classification and bounded-resource acceptance defects before any new model execution. Base commit/tree: `0047a050803c29ea928022e7d3e8ba035fedb866` / `git rev-parse HEAD^{tree}` at branch creation. Evidence class: source audit and model-free mutation tests; historical raw is reaudited separately.

Alternatives: retain the old comparator, or weaken the claim. Decision: enforce the frozen stage/chunk/shape/stride/byte/file set, derive location from values, require process identity and every sampled guard, reject JSON float overflow, and record actual mapped backend libraries prospectively. Historical manifests without launch identity or maps do not gain those receipts retroactively. No backend runtime source was changed.

Tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c7_gate_repair tools.test_c5_compare tools.test_c2_gate tools.test_c3_approval tools.test_c3_terminal_sample` — 52 PASS. The previous focused 41 PASS also ran before the new tests. Synthetic invalid captures and resource mutations fail; a valid capture including masked zero rows passes. A no-model C6 raw recomputation is recorded in the C7 evidence unit, not in this code commit.

Failures/limits: C6 historical resource and mapping identity is incomplete. The C3 server gate has independent launch identity checks, but old C6 `run_bounded` manifests did not. Next discriminating gate: reaudited raw claims plus a frozen C7 protocol and conservative capacity accounting before full-model admission.
