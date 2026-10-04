# C257 — selected real-head multi-grid fidelity

Decision: PASS_SELECTED_REAL_HEAD_MULTIGRID (MEDIDO_NO_TARGET), measurement HEAD a6cf8c668878e5d17aad2be323cf2a96432e7c4c. Both development classes (RLE code and structured route) passed the selected all/first/middle/last rejection and partial-grid continuation checks. The diagnostic used real head proposals plus explicitly recorded target-oracle overrides for coverage. Overrides are excluded from any production performance claim.

Each process confirmed 16 new tokens after its separately counted prefill anchor. Five verification calls generated 40 full vocabulary rows. Four deliberately constructed acceptance/rejection patterns and a subsequent unmodified head step were checked against independent clean prefix-only, deterministic-padding references. All consumed rows were bitwise equal and finite. The native diagnostic actually made 40 target calls per process including oracle construction, clean references and restoration; five verification calls alone do not describe its total work.

The fixed-grid R1 target is distinct from n1 R0 arithmetic. This result qualifies the observed greedy boundary and head KV/feature-state continuation, not general quality, stochastic sampling or universal causal invariance. EOS, near-context-edge cancellation and natural functional utility remain uncovered. Complete vector files, proposals, inputs and outputs remain local in the raw manifest.

Physical envelope: 246.0291599100019 s. Resources and immutable raw hashes/sizes are recorded under results/c257-eagle3-multigrid-fidelity-20261004/. Diagnostic dump/reference time is not production timing. No default, service or operational preset changed. The own systemd unit was observed inactive afterward, GPU total returned to 13 MiB, and the pre-existing Ollama/bridge processes remained.

Next: C258 actual unmodified-head native development discriminator, with no oracle or full-vector dump during timing. An integrated decode improvement is necessary before a functional 2K utility screen; a short 32-token loop alone cannot qualify useful product latency or M4.
