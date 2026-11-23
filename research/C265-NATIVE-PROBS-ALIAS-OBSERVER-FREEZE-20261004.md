# C265 — observe the actual native biased ADD

## Correction of the investigator's source interpretation

C264 remains FAIL_UNIT_PRESERVED. Its observer stopped because the claimed biasADD alias was actually I32 ARGSORT. The prior C264 freeze's source explanation was incorrect; it is not amended retrospectively. `ggml_argsort_top_k` returns a VIEW of I32 ARGSORT, so `selected_experts->src[0]` is the sorting node. For GPTOSS SOFTMAX_WEIGHT, `probs=logits` renames the F32 biasADD to **ffn_moe_probs**. C127's original index independently exposes F32 logits and F32 probs and lacks the optional original biased name. This is SOURCE_AUDITED, not a model numerical mismatch.

## Narrow repair and counterproof

Observer captures the actual exact-named native probs F32 ADD with128 expert rows and original broadcast bias operand. It records native_name plus the canonical biased-logit stage; no reconstruction of logits, no synthetic payload. The actual `ggml_argsort_top_k` helper in model-free metadata tests returns VIEW/I32 ARGSORT, which the observer ignores, while accepting its F32 biasADD input and rejecting an unbiased nonADD labeledprobs. Exact-name view/cont rejection and all-five-consumer lifetime counterproof also pass. Directed216-stage cardinality/shapes/finite/witness/bitwise gates are unchanged.

New C265 root and binary; private source/library identity93151fc4, official inputs, R2 shape153/FFN32×4+25,20GiB common instrumentation cap/high, swap0, preventive margin and thresholds remain. Two fresh R2tile/reuse processes, each inventory60s/freshness3s,240s run and30s post gate, family740s/raw600MiB. Existing C262 R0 selected bridge is reused only for equal original shapes/devices/payloads; no36FFN repetition. The old C262/C263/C264 binaries, attempts, partials and FAIL/NOT_RUN persist.

Successful same-profile capture is only numerical admission. Independent selected canonical whole-span-router/32/25 FFN references, instrumentation neutrality, production latency, causal/functional qualification remain conditional. No M4/default/opt-in promotion or remote publication.
