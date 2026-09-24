# cb_eval intercept bound: scheduler semantics correction

Date: 2026-09-24

Failed campaign: `results/cb-eval-intercept-bound-20260924T173415Z/`.

Evidence class: `MEASURED_EXECUTION_FAILURE + STATIC_PINNED_SOURCE_AUDIT`.

## Finding

The first campaign reached the callback and returned exit code 2 because the
capture executable required `llama_decode` to return 2. The preserved stderr
records that `llama_decode` instead returned 0 after the cancel callback.

The pinned `ggml_backend_sched_graph_compute` implementation explains this:
after a callback returns false, it breaks its node loop and then returns
`GGML_STATUS_SUCCESS`. This is a scheduler early stop, not propagation of
`GGML_STATUS_ABORTED` through `llama_context::decode`.

## Repair

The bounded experiment still measures the intended zero-Tesy-work interval:
the cancel callback stops after final routing weights, and the code asserts
that `ffn_moe_out-0` was not reached. The native tool now requires return code
0 and records it as `decode_return_code` in raw output.

Because success does not provide abort rollback, the tool explicitly removes
the repeated token at the prompt-length position with `llama_memory_seq_rm`
after timing each trial. The rollback occurs after the endpoint timestamp and
is excluded from both arms. Route IDs and exact routing weights remain
required to be identical across all trials.

## Frozen items retained

The model, prompt, pin, CPU-only configuration, token `2167`, selected
experts, routing-weight tensor, warmup count, 81 sample pairs, order, timing
boundary, median/p95 hard-NO_GO inequalities and decision labels are unchanged.

## Decision

The original campaign root remains a failure and supplies no feasibility
conclusion. Rebuild at a successor commit and use a new output root for the
corrected campaign. This correction does not make `SURVIVES` a performance GO
and does not authorize prefetch.
