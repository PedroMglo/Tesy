# C57b synthetic FFN discriminant

- Objective: test whether the shared activation repair survives gate/up/down, biases, active-pair mask and reduction with two tokens and poisoned scratch.
- Base: old C48 backend `0bc5c75c273abaa34e51d0af932a96969665c3a3`; isolated repaired backend `aac3bbde35575044d290798a120cde038f85b670`.
- Evidence class: REPRODUZIDO_MODEL_FREE. The graph is synthetic and does not substitute for the 120B layer or attention/KV reference.
- Alternative: the repaired MMID may pass alone while a later bias, mask or reduction contaminates an active output. The test compares the final reduced output against a control with parked IDs replaced by valid IDs while keeping the original mask.
- Contract: MXFP4/F16/F32 weights, one broadcast activation row for four ID pairs, two tokens, gate/up/down GGML MMIDs, biases, OAI SwiGLU, mask, pair reduction, four threads, and 0x00/0x7f scratch poison. Active inputs include finite values and signed zero. The repaired result must be bitwise equal to its control and finite; parked pairs must not contribute.
- Known limit: the synthetic graph adds per-pair biases through plain GGML add, because the operator's `ggml_add_id` asserts nonnegative IDs; it is not a byte-for-byte reconstruction of the streaming graph. Full model boundary, routing and canonical layer reference remain NOT_RUN.
- Decision: a model-free pass permits a fresh physical numeric boundary under a frozen backend/build and resource policy; it does not promote C48 or C57 performance.
