# C125b — exact-offset direct I/O component screen

**Decision: `NO_GO_MODEL_FREE_COMPONENT_PARALLELISM` on the C123 fixed decode load sequence.** Four ABBA read-only O_DIRECT arms passed within the E18/zero-swap scope, AC/performance and live thermal/resource checks. Each read the same 19,947,772,800 logical bytes from the original GGUF offsets, in 1012 `(call, layer)` groups containing 1509 observed expert loads. No weights, tensor computation, routing, user service or default were changed.

| Pair | Four-worker serial | Twelve-worker component parallel | Paired gain |
|---|---:|---:|---:|
| 1 | 10.181 s | 10.420 s | −2.352% |
| 2 | 10.317 s | 10.443 s | −1.223% |

Median paired gain was **−1.787%**, below the prospective ≥15% investment gate, with neither pair positive. The observation does not prove that every asynchronous I/O design is slower: this probe fixes the C123 miss stream, adds a barrier per observed layer, includes Python submission overhead, and does not reproduce server compute, prefetch, H2D or physical NVMe exclusivity. It does show no material read-only advantage from simply issuing each selected expert's three component reads concurrently under this exact workload and drive state. A backend patch for this hypothesis is not justified.

C125's earlier freeze serialization failure remains separately preserved as `FAIL_HARNESS_FREEZE_PREMODEL_JSON_PATH`; C125b used source `4b9b650ff6ba4f809e74fad4b48aa244fb782057` and measurement commit `27e46fa5c5e01be6b154ff3de4a4792942fc5e5c`. Raw arm receipts and hashes are in `results/c125b-component-io-probe-20260929T1555Z/`. The next cheap discriminator is a primary-slot quota simulation from authoritative C123 DEMAND events with a source-faithful baseline check; only a material saving under the same total RAM/VRAM budget should lead to a new numeric profile. If that check fails, pivot to the bounded backend/loader capability path rather than building L2. C124's server confirmation and M3/M4 classifications are unchanged.
