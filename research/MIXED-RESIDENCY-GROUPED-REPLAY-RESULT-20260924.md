# Grouped mixed-residency replay result

Date: 2026-09-24
Branch: `research/mixed-residency-diagnostic-20260924`
Base commit: `d6cc936b4b5f6029657090d742c40ec82bc90287`
Base tree: `f714856ccd7597d36d8690f10cfcf5b3ac217175`
Initial worktree: clean
Evidence class: `TRACE_DERIVED_RESIDENCY_OPPORTUNITY`

## Objective and inputs

Reproduce the admitted 4 GiB demand-triggered byte-LRU expert hit rate, then
count the number of hits in each one-token top-4 routing group. The parameters
were fixed by `MIXED-RESIDENCY-DIAGNOSTIC-PROTOCOL-20260924.md` before this run:
4 GiB, `min_graph_seq=1`, native routing trace and native expert inventory.

- Trace: `results/bringup-20260923T205424Z/trace-exactness/routing.jsonl`;
  SHA-256 `4462cfeba898ef1ffb8dd88c36b41ad03e723b6e6b3d2bc31365fec98b00cd35`.
- Inventory: `results/native-expert-inventory-20260924T085418Z/expert-inventory.json`;
  SHA-256 `8f188fdeadd1f2d0c29f9b58b94b5f5c4e390c0da2a0da5c716b759def456269`.
  It reports 24 layers, 32 experts/layer and 13,253,760 encoded bytes/expert.
- Output: `results/mixed-residency-opportunity-20260924T104610Z/histogram.json`;
  SHA-256 `ba9e989d9713f8fd5d51ebd5112c8f0e6f12e4af821e2e7eceb408ed5ba423ab`.
  The output remains ignored by Git.

## Failure and correction

The first model-free gate failed one assertion in
`test_mixed_residency_histogram_tracks_top4_hits_before_insertions`. Its
synthetic cache holds eight experts, so the third group `(0, 1, 2, 3)` has
four hits, not two. The test already expected six total hits, consistent with
per-group counts 0, 2 and 4. Only the incorrect histogram expectation and the
misleading test name were corrected. The simulator, inputs, capacity, baseline
and acceptance threshold were unchanged.

Alternatives considered: changing cache semantics or capacity would change the
admitted replay contract merely to satisfy an incorrect assertion. Replaying
the three synthetic groups under the existing byte-LRU semantics resolves the
contradiction without such a change.

## Tests and result

- `git fetch --prune origin`: PASS; the local base matched the remote branch.
- Ruff on the two focused files: PASS.
- `compileall` on the two focused files: PASS.
- `pytest -q tests/test_mixed_residency.py`: 3 passed after correction; before
  correction, 1 failed and 2 passed.
- Trace SHA-256 and inventory schema/status/shape checks: PASS.
- Grouped replay and schema, class, expert-use, histogram-sum and admitted
  66.25% hit-rate checks: PASS.

| GPU hits in top-4 | Groups | Fraction |
| ---: | ---: | ---: |
| 0 | 39 | 10.833333% |
| 1 | 26 | 7.222222% |
| 2 | 62 | 17.222222% |
| 3 | 128 | 35.555556% |
| 4 | 105 | 29.166667% |

There are 360 routed groups across 15 one-token graph IDs and 1,440 expert
uses. The replay has 954 hits (66.25%) and 486 misses. Mean hits per group are
2.65; mean misses are 1.35. The aggregate matches the admitted LRU replay.

## Decision and limits

Stage A passes. The result shows which top-4 compositions occur under the
ideal timely-insertion LRU simulation. It does not measure actual GPU
residency, physical transfer bytes, prefetch accuracy, mixed FFN latency or
full-model speed. The 15 graph IDs are a trace-derived committed-token proxy,
not a fresh exactness measurement. No physical mixed-execution test was run.

Next discriminating gate: Stage B should validate numerical parity and measure
isolated mixed top-4 execution through the pinned ggml path, prioritizing the
common 3-hit and 4-hit cases while retaining the frozen all-CPU reference and
freezing numerical correctness thresholds before physical timing.
