# C236 — conditional EAGLE-3 boundary, no head execution

SOURCE_AUDITED original reconstructed C75 tree45b2b5b97353845d9d982a06f20c4f2f420528e2. A1 width2 economic screen NO_GO; width4 currently under frozen measurement. No head weights downloaded, converted or loaded. Head integration remains conditional on semantic and economic A1 gates; this note is a narrow source plan, not qualification.

## Existing native boundary

common/speculative.cpp draft_eagle3 enables three target layer-input embeddings, copies/interleaves host F32 features, encodes in draft-ubatch chunks, copies the encoded states and keeps per-sequence deferred boundary plus verification state. Decoder convention pairs token[P+1] with feature[P] at memory positionP. Rejection must restore deferred state, target/draft KV and sampler/parser correctly. Source greedy target acceptance compares target samples with proposed tokens through first divergence; no stochastic p/q claim.

conversion/llama.py supports LlamaForCausalLMEagle3 and requires target config metadata, not target weights. It writes target layer-input indices[2,18,33] for36 layers. Pinned NVIDIA config declares auxiliary state IDs[1,17,32]. The probable output-versus-next-layer-input correspondence is INFERIDO until the upstream training/extraction contract and residual/norm locations are checked. Do not silently use a mismatched feature contract. Converter applies tensor renaming and RoPE Q/K permutation; preserving source BF16 values and GGUF-supported types must be checked before conversion.

src/models/eagle3.cpp has optional own embedding/output tensors and can use ctx_other target embedding/output when omitted. Sharing a tensor is SOURCE_AUDITED; actual scheduler placement, transfer/workspace and alias ownership are NOT_RUN. server-context.cpp post_decode rejects speculative indices split between sub-batches: start single sequence, complete fixed blocks within ub32, no assertion bypass.

## Numeric target and rejection cost

Selected C243/C244 evidence supports a fixed-grid R1 with prefill origin and widthB fixed, prior complete grids rebuilt from confirmed input IDs, and deterministic zero padding of unknown positions. Different proposal length/rejection cannot slide the grid origin or select a new shape silently. Existing generic server speculation may restart a batch at a rejection boundary: that is not automatically this R1. A narrow adapter must retain fixed grid alignment, reconstruct partial-grid known inputs after rejection and charge recomputation R. R1 depends only on confirmed prefix and fixed metadata, never draft-future IDs. It is a declared numerical profile, not universal R0 equality. Context/cap/EOS must stop before unqualified shape changes; emitted tokens remain target-verified only.

Feature extraction can alter materialization/fusion: before using features, compare full selected logits and continuation with the existing A1 production path under a new identity. Features are not silently free. Perfect-assist D0/Rideal curves are investment bounds; real draft encoding, prefill, K decoder proposals, full target verification, discarded work, recomputation and all materialization enter the integrated benchmark.

## Capacity estimate, conditional only

FORMAL arithmetic on pinned config dimensions, not measured footprint: fc8640x2880; Q5760x4096; K/V5760x512; O4096x2880; three FFN matrices2880x17280 give215,470,080 matrix values,430,940,160 bytes at BF16 before norms/metadata/alignment. This explains the roughly431MB published file and excludes shared target vocabulary matrices. One F16 KV layer with eight64-dimension KV heads at8192 positions is16MiB for keys+values before padding; F32 concatenation is34,560 bytes per input row. Actual caches, graphs, staging, allocators and transient copies remain DESCONHECIDO. Admission uses live measured total VRAM and one prospectively chosen common cap, not these logical parameter bytes alone.

## Conditional external identity

Only nvidia/gpt-oss-120b-Eagle3-long-context revision633caf45f31288cbb70ee237f7c939db707ecc94 is authorized. Resolve exact file size/LFS OID/hash, freeze manifest before download and verify bytes afterwards; weights<=768MiB, metadata<=32MiB, derived GGUF<=2GiB. Existing metadata-only CLI dry-run is not a weights download. No target HF weights, alternative head or mutable main dependency.

Primary pinned [configuration](https://huggingface.co/nvidia/gpt-oss-120b-Eagle3-long-context/blob/633caf45f31288cbb70ee237f7c939db707ecc94/config.json) and [model card](https://huggingface.co/nvidia/gpt-oss-120b-Eagle3-long-context/blob/633caf45f31288cbb70ee237f7c939db707ecc94/README.md). External reported TensorRT-LLM/B200 acceptance is not a forecast for this laptop. No architecture novelty claim, operational promotion, M3/M4 or remote publication.
