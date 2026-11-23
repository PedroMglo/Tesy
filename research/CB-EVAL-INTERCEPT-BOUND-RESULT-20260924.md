# cb_eval interception zero-work bound result

Date: 2026-09-24

Protocol: `CB-EVAL-INTERCEPT-BOUND-PROTOCOL-20260924.md`, with the pinned
scheduler-semantics correction in
`CB-EVAL-INTERCEPT-BOUND-SCHEDULER-SEMANTICS-CORRECTION-20260924.md`.

Measurement commit: `7490803adc187fdb59dbc056ada081a045bdb2ac`.
Measurement tree: `399ecc9db660b71b89730654d9cb709400d11e75`.
Successful campaign: `results/cb-eval-intercept-bound-20260924T173809Z/`.
Preserved failed campaign: `results/cb-eval-intercept-bound-20260924T173415Z/`.

## Objective and evidence class

Measure the minimum scheduler/callback cost after the real stock layer-0
router has produced its final routing weights, with no Tesy FFN work. This is
a measured lower bound for a possible external cb_eval boundary. It is not a
routed-layer timing measurement and does not establish a performance benefit.

## Failure, correction and provenance

The first root failed because the original program required decode return code
2. Pinned scheduler source shows that a false eval callback breaks graph
execution then returns success, so `llama_decode` returns 0. The old root and
its `failure.json` are preserved. The correction explicitly rolls back the
repeated token from KV memory after each timed endpoint, records return code
0, and leaves the model, route, timing boundary, sample schedule and
hard-NO_GO inequalities unchanged.

- Focused model-free validation: PASS, 17 tests.
- Full model-free validation: PASS, 238 tests.
- llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691`; worktree clean.
- Native build provenance PASS. Capture SHA-256
  `c262798adcfe5771a5aeb0375297ed278c64540a21556d0d262adc3eacc091ee`.
- Process identity and exact argv PASS.
- Resource telemetry PASS: 23/23 valid GPU samples, zero failed samples,
  zero process swap, 48 C maximum GPU temperature and 26.8 W maximum GPU
  power. No `failure.json` exists in the successful root.

## Result

The repeated live stock route was stable: decode token `2167`, top-k experts
`[1, 13, 17, 21]`, and final tensor `ffn_moe_weights_softmax-0`. There were 6
warmup pairs and 81 measured pairs in frozen alternating order.

| Metric | Stock MoE segment | Scheduler early stop | Ratio |
| --- | ---: | ---: | ---: |
| Median | 2.675066 ms | 0.049904 ms | 0.0186552 |
| p95 | 2.873420 ms | 0.057839 ms | 0.0201290 |

Both cancel values are strictly below their stock comparators. The recorded
decision is `CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

## Limitations and next discriminating gate

The bound excludes activation handoff, Tesy serial/async FFN execution,
reinjection, logits, sampling, full-model throughput, physical traffic,
residency policy and prefetch. It also uses one route on one physical run.

The next gate is a separately frozen real handoff experiment: keep the stock
router and final routing weights authoritative, transfer the activation to
Tesy serial/async execution, establish output/reinjection correctness, then
measure only after exactness passes. No prefetch is authorized by this result.
