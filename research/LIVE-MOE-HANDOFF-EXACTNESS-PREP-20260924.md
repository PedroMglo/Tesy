# Live MoE handoff exactness preparation

Date: 2026-09-24

Branch:
`research/live-moe-handoff-exactness-20260924`

Development base:
`research/live-moe-integration-feasibility-20260924`

Evidence class:
`SOURCE_AUDITED / IMPLEMENTED_NOT_RUN / PHYSICAL_NOT_RUN`.

## Admitted prerequisite

The corrected physical zero-Tesy-work cb_eval campaign returned:

`CB_EVAL_INTERCEPT_BOUND_SURVIVES`.

Measured on the repeated admitted route:

- stock MoE median 2.675066 ms;
- early-stop median 0.049904 ms;
- median ratio 0.0186552;
- stock MoE p95 2.873420 ms;
- early-stop p95 0.057839 ms;
- p95 ratio 0.0201290;
- 23/23 GPU resource samples valid;
- zero process swap.

The preserved first root established that the pinned scheduler early-stop
semantics return success from `llama_decode`; the corrected runner explicitly
rolls back the repeated KV position after each endpoint.

This prerequisite authorizes a real activation handoff correctness gate only.

## Selected boundary

Do not patch Transformer math yet.

Reuse the public stock callback boundary and the already validated compact Tesy
expert executor in a single process.

The new opt-in mode is:

`tesy-mixed-residency --live-handoff-exactness`.

It links the mixed-residency tool to pinned `llama` in addition to `ggml`.

Existing default, overlap and routed-replay modes are unchanged.

## One-process sequence

1. initialize Tesy CPU/CUDA backends;
2. load the same GGUF through stock llama.cpp with `n_gpu_layers=0`;
3. prefill the frozen raw prompt with callback state disabled;
4. greedily sample and require token `2167`;
5. stock-reference arm:
   - capture `attn_post_norm-0`;
   - capture top-k;
   - capture final softmax routing weights;
   - capture stock `ffn_moe_out-0`;
   - early-stop after stock output;
   - require decode return 0;
   - explicitly roll back the repeated position;
6. live-handoff arm:
   - repeat token `2167`;
   - capture the same activation/top-k/final weights;
   - early-stop at final routing weights before stock MoE;
   - require decode return 0;
   - explicitly roll back the repeated position;
7. compare stock-reference and handoff route/activation;
8. use the handoff-arm activation to execute Tesy h=2/h=3 serial and async;
9. compare all Tesy outputs against stock-reference `ffn_moe_out-0`.

No activation file or second process mediates the handoff.

## Frozen identities

Token:

`2167`.

Experts:

`[1, 13, 17, 21]`.

Routing weights:

exact F32 vector equality between the two live arms.

Final weight tensor:

`ffn_moe_weights_softmax-0`.

Controlled partitions:

- h=2: slots 0..1 GPU;
- h=3: slots 0..2 GPU.

The stock route remains authoritative.

## Activation exactness

Record whether stock-reference and handoff activations are bitwise equal.

Bitwise equality is diagnostic only.

Gate on the existing numerical thresholds:

- relative max <= 0.005;
- cosine >= 0.9999;
- finite values.

This preserves the project's distinction between bitwise equality and
numerical parity.

## Tesy output exactness

For h=2 and h=3 require:

- serial vs stock PASS;
- async vs stock PASS;
- async vs serial PASS.

The stock-reference `ffn_moe_out-0` is the authority.

The existing `run_routed_exactness` path is reused and contains no timing
loop.

## Native output

Schema:

`tesy.live_moe_handoff_exactness.v1`.

Decision:

`LIVE_MOE_HANDOFF_EXACTNESS_GO`.

The native result records:

- both early-stop return codes;
- both rollback booleans;
- activation bitwise flag;
- activation numerical parity;
- route IDs/weights;
- h=2/h=3 parity triples.

No timing fields are emitted.

## Independent validator

New module:

`tesy.live_moe_handoff_exactness`.

It rejects:

- wrong schema/classification;
- token/route drift;
- return code drift;
- failed rollback;
- malformed weights;
- activation parity failure;
- h=2/h=3 output parity failure;
- threshold drift;
- premature decision labels;
- timing fields in the correctness schema.

## Physical runner

New runner:

`scripts/run_live_moe_handoff_exactness.sh`.

It is fail-closed and no-replace.

Before execution it validates:

- clean Tesy and llama.cpp checkouts;
- model and prompt hashes;
- physical reference host;
- no competing GPU compute process;
- routed-layer build provenance bound to the current mixed/capture sources,
  CMakeLists and executable bytes.

The live mixed process is SIGSTOPped only after the build CUDA library is
mapped so executable, exact argv and mapped `libggml-cuda` provenance can be
validated. It is then SIGCONTed.

This gate has no timing metric, so provenance instrumentation cannot alter a
performance conclusion.

Resource requirements remain:

- complete GPU telemetry;
- zero process swap;
- >=1024 MiB sampled GPU free headroom;
- >=2048 MiB sampled host MemAvailable.

## Source/static validation completed

**REPRODUZIDO / PASS**:

- pinned llama public context fields were checked before use;
- pinned early-stop return-code semantics come from the corrected preceding
  campaign;
- stock-reference and handoff callbacks use named stock tensors;
- handoff arm returns false at final routing weights;
- handoff arm explicitly fails if stock `ffn_moe_out-0` is reached;
- both repeated positions are explicitly rolled back;
- exact route equality is checked before Tesy execution;
- admitted token/expert identity is fail-closed;
- handoff activation, not prior campaign files, feeds Tesy;
- existing h=2/h=3 exactness executor is reused;
- live handoff and routed exactness functions contain no timing loops;
- output validator rejects timing fields;
- output reinjection and committed-token continuation remain explicitly out of
  scope.

## Tests not run in this environment

Focused Ruff/compileall/pytest:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Full model-free suite:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Shell syntax:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

Native compile:
`NOT_RUN_REFERENCE_HOST`.

Physical live handoff exactness:
`NOT_RUN_REFERENCE_HOST`.

## Next gate

If `LIVE_MOE_HANDOFF_EXACTNESS_GO`:

freeze a separate timing protocol for the same exact live boundary before
collecting any latency samples.

That timing remains handoff feasibility, not end-to-end routed inference,
until output reinjection/continuation correctness is separately established.

If this gate fails:

do not time the handoff, do not implement prefetch, and diagnose or kill the
boundary under a new campaign identity.
