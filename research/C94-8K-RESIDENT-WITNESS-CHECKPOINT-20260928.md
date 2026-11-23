# C94 witness checkpoint: 8K resident FFN

- **Objective/base:** compare C93 8K preload-ON wave-ON captured activations with a same-build resident C75 layer. Source `7555fd7444cc89d1ff1052d7ab524ce811bfcb7f`; measurement `4054e5cc766d591c28348d4b309b68cf60f58cd4`. C93 raw hashes and 250-state coverage were verified before loading any reference layer.
- **Evidence:** layers 25,26,27,28,24,29 each returned `PASS_CANONICAL_LAYER`, 42/42 numeric rows with ordered routing IDs, routing weights and FFN output bitwise. No masked row falls in these layers. **MEDIDO_NO_TARGET** for isolated FFN, one layer per E16 process.
- **Alternative/limit:** remaining 30 layers and last-layer masked states remain **NOT_RUN**; attention/KV, server behavior and quality are independent. The witness does not certify full 8K numeric coverage by itself.
- **Decision:** preserve witness PASS and proceed only to the 30 frozen remaining layers. Historical C48/C78/C91 failures unchanged. No default or remote change.
