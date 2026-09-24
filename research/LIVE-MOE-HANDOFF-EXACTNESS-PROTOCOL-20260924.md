# Live MoE handoff exactness protocol

Date: 2026-09-24

Branch:
`research/live-moe-handoff-exactness-20260924`

Prerequisite:
`CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

Pinned llama.cpp:
`4e416ee7308dd6b581796f1a6241276cd5982691`.

Evidence class:
prospective correctness-only live handoff diagnostic.

## Objective

Test the smallest real in-process handoff:

`stock router -> live activation/top-k/final weights -> Tesy serial/async FFN`

without timing it.

The target stock router remains authoritative. Tesy does not recompute,
predict, reorder, reduce or replace top-k routing.

This gate must establish that the activation captured at the real live
handoff boundary can drive the existing Tesy h=2/h=3 compact expert execution
and reproduce stock `ffn_moe_out-0` before any handoff timing is authorized.

## Why this follows the cb_eval bound

The corrected physical zero-work callback bound measured:

- stock MoE median 2.675066 ms;
- early-stop median 0.049904 ms;
- stock MoE p95 2.873420 ms;
- early-stop p95 0.057839 ms.

Decision:

`CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

That only showed that scheduler early-stop overhead does not kill the external
handoff boundary by itself. It supplied no activation-transfer or Tesy FFN
correctness evidence.

## Frozen model and workload

Model:
`gpt-oss-20b-mxfp4.gguf`.

SHA-256:
`52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`.

Size:
`12109564352` bytes.

Prompt:
`benchmarks/prompts/b0-b1-diagnostic.txt`.

Prompt SHA-256:
`431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6`.

Stock context:

- `n_gpu_layers=0`;
- context 4096;
- threads 12;
- raw committed prompt;
- greedy first-token sampling;
- layer 0.

Frozen admitted decode token:

`2167`.

Frozen admitted expert IDs:

`[1, 13, 17, 21]`.

Final routing-weight tensor:

`ffn_moe_weights_softmax-0`.

Any token or expert-ID mismatch terminates the campaign.

## Single-process construction

The `tesy-mixed-residency` executable is linked to the pinned llama.cpp
library only for this opt-in mode.

One process owns:

- the stock llama.cpp model/context;
- the existing Tesy CPU backend;
- the existing Tesy CUDA backend;
- compact real expert tensors loaded from the same GGUF bytes.

No second executable, temporary activation file or subprocess handoff is used.

## Prefill

Install the passive callback when creating the stock context, but keep its
state disabled during prompt prefill.

Run the frozen prompt normally and greedily sample the first token.

Require:

`decode_input_token == 2167`.

## Stock-reference arm

Enable the callback for the repeated token.

Capture:

- `attn_post_norm-0`;
- `ffn_moe_topk-0`;
- `ffn_moe_weights_softmax-0`;
- `ffn_moe_out-0`.

At `ffn_moe_out-0`, return false to early-stop the remaining graph.

Pinned scheduler semantics require:

`llama_decode == 0`.

Persist the captured activation, route, final weights and stock MoE output in
process memory.

Then explicitly remove the repeated decode position from the stock memory with
`llama_memory_seq_rm`.

Rollback must return true.

## Live handoff arm

Repeat the exact same decode token after the stock-reference rollback.

Capture:

- `attn_post_norm-0`;
- `ffn_moe_topk-0`;
- `ffn_moe_weights_softmax-0`.

At the final routing-weight callback, return false.

The handoff arm must **not** reach `ffn_moe_out-0`.

Require:

`llama_decode == 0`.

Then explicitly roll back the repeated position again with
`llama_memory_seq_rm`.

Rollback must return true.

## Route identity

Between stock-reference and handoff arms require exact equality of:

- top-k expert IDs;
- all four F32 routing weights.

The route must also equal the admitted expert IDs
`[1, 13, 17, 21]`.

No aliases, remapping or subset re-softmax are allowed.

## Activation exactness

Compare the 2,880-F32 stock-reference activation and live-handoff activation.

Record:

`activation_bitwise_equal`.

Bitwise equality is diagnostic only and is **not** required.

The gate requires numerical parity using the already frozen thresholds:

- relative max error <= 0.005;
- cosine similarity >= 0.9999;
- all values finite.

This explicitly distinguishes bitwise equality from numerical parity.

## Tesy expert execution

Only after both live arms and rollbacks pass, execute the existing compact
real-expert path using the activation captured from the **handoff arm**.

Controlled partitions:

- h=2: top-k slots 0..1 GPU, 2..3 CPU;
- h=3: top-k slots 0..2 GPU, 3 CPU.

The exact stock expert IDs and exact final routing weights are preserved in
their original slot order.

For each h execute once:

- serial Tesy FFN;
- async Tesy FFN.

No timing loop is entered.

The stock-reference `ffn_moe_out-0` is the numerical authority.

## Output exactness

For h=2 and h=3 require:

- serial vs stock PASS;
- async vs stock PASS;
- async vs serial PASS.

Frozen thresholds:

- relative max error <= 0.005;
- cosine >= 0.9999;
- finite values.

Any mismatch terminates the campaign.

## Decision

Only if all route, rollback, activation and h=2/h=3 output gates pass:

`LIVE_MOE_HANDOFF_EXACTNESS_GO`.

There is no NO_GO performance label in this correctness campaign. Any failure
is preserved as a failed campaign and investigated under a new identity.

## Build boundary

`tesy-mixed-residency` now links to `llama` as well as `ggml`.

The existing routed-layer build provenance remains authoritative and must bind:

- current clean Tesy HEAD;
- pinned clean llama.cpp HEAD;
- current mixed-residency source SHA-256;
- current capture source SHA-256;
- native CMakeLists SHA-256;
- both native executable SHA-256 values;
- resolved executable paths.

The physical runner recomputes all bound values before launch.

## Runtime provenance

The live handoff process uses both CPU and CUDA backends.

Before allowing the process to continue:

- freeze exact argv;
- wait for the build's `libggml-cuda.so` mapping;
- SIGSTOP the process;
- verify live executable;
- verify exact argv;
- verify the unique mapped build CUDA backend;
- SIGCONT.

This instrumentation is outside any performance measurement because this gate
contains no timing result.

## Resource gates

Sample runtime resources.

Require:

- at least one sample;
- complete GPU telemetry;
- zero process swap;
- sampled GPU free headroom >= 1024 MiB;
- sampled host MemAvailable >= 2048 MiB.

Resource data qualifies campaign health only.

## Output schema

Native:

`tesy.live_moe_handoff_exactness.v1`.

Summary:

`tesy.live_moe_handoff_exactness_summary.v1`.

Classification:

`MEASURED_LIVE_MOE_HANDOFF_EXACTNESS`.

The validator rejects timing fields such as:

- `median_ms`;
- `p95_ms`;
- `samples_ms`;
- `speedup`.

## Failure policy

Output root is no-replace.

Preserve `failure.json` on any failure.

Stop on:

- dirty Tesy/llama.cpp checkout;
- wrong HEAD/model/prompt/pin;
- physical-host identity failure;
- competing GPU compute process;
- stale build provenance;
- live executable/argv/CUDA mapping mismatch;
- wrong token or route;
- malformed/non-finite routing weights;
- stock-reference or handoff decode return != 0;
- failed stock-reference rollback;
- failed handoff rollback;
- handoff arm reaching stock MoE output;
- activation numerical mismatch;
- serial/async output mismatch;
- OOM;
- resource telemetry failure;
- swap/headroom violation.

Debugging uses a new campaign identity.

## Explicit exclusions

This gate does not establish:

- handoff latency;
- serial/async speedup;
- full-layer latency;
- output reinjection correctness;
- committed-token continuation;
- TTFT, TPOT or tok/s;
- cache/residency policy;
- prefetch;
- physical PCIe/DRAM/NVMe traffic;
- bytes per token;
- run-to-run stability;
- speculation;
- novelty.

## Next gate

If `LIVE_MOE_HANDOFF_EXACTNESS_GO`:

freeze a separate prospective timing protocol for the exact same live boundary
before taking any latency samples.

That future timing remains a handoff-feasibility result until output
reinjection/continuation is separately established.

If exactness fails:

do not time the handoff and do not advance to prefetch.
