# C259 — selected expert-major reuse numerical PASS

MEDIDO_NO_TARGET: all six new CPU processes passed. Measurement HEAD9d0c126. Three original disjoint numerical tiles32/32/29, layers0/12/24, pool40, four native workers, original MXFP4 slices/routing/biases and ordered pair reduction. Every complete selected FFN output was finite and bitwise equal to its C127 native/canonical reference; reconstructed source/device/output identity chain via C237 is preserved. This is not numerical qualification of unobserved attention, GPU tile shapes or full prefill.

| CPU layer | Control actual loads | Reuse actual loads | Control byte components | Reuse byte components |
|---|---:|---:|---:|---:|
| 0 | 117 | 79 | 1026 | 474 |
| 12 | 67 | 64 | 684 | 384 |
| 24 | 88 | 68 | 804 | 408 |

The six-component witness covered all active unique tile/expert combinations at the consumer boundary, including generation/resident/keep and O_DIRECT bytes. Actual generations equaled demand plus preload reservations. Preloads are not free. A's loads are observed; the sum of individual tile expert unions171/114/134 is not substituted for A's actual loads. B served each selected union exactly once. This demonstrates genuine load reuse in these selected operator inputs, rather than loop reorder with unchanged reloads.

4GiB common cap/high and swap0 passed the live guards, own inventories and library mapping. Physical envelope381.554187889s. Numeric service includes extra byte checks and is not production timing. Raw manifests, resource samples and per-arm receipts remain under results/c259-expert-reuse-inventory-repair-20261004/. Next admitted unit C260 measures complete native service without byte witness in its timing interval. LOCAL_ONLY, no operational preset/default change.
