# C262 — bounded native layer executor, numerical admission

## State and authority

Continuation of the same accepted post-C235 epoch, branch `campaign/120b-block-verifier-expert-reuse-20261004T105527Z`, base `8c78f598e446b1b09fb3ba518b77e0d7496bfa47`. C258 real-head development was negative; C259/C260 selected CPU reuse passed. C261 revalidated the existing slots40 server trace and identified a conditional prefill opportunity, not a speedup. Historic results and the original operational build remain intact. LOCAL_ONLY; no publication authorization.

## SOURCE_AUDITED boundary

Private backend `backends/c262-layer-expert-reuse`, descendant of reconstructed C75 tree `45b2b5b97353845d9d982a06f20c4f2f420528e2`. Patch is retained under `patches/`. Existing attention/KV/router and streaming loader are reused. An explicit reserved span153 and C-API mode setter allow the same native model to process a bounded layer span; continuous concurrent sequences and other sizes are rejected. Original mode0/default remains ub32.

```
153-position native attention/router
  -> five FFN tiles 32/32/32/32/25
  -> original gate/up/SwiGLU/down kernels and logical biases
  -> ordered per-pair wave accumulation and routing-weight/top-k reduction
  -> next layer, existing causal attention/KV; decode remains n1
```

R2-tile has separate native wave plans for five tiles (38 callbacks). R2-reuse has one authoritative expert union, eight wave callbacks, each serving all five tiles before replacing any slot. Dependencies include all five consumers, not just the last. Byte checks validate expert/slot/generation/resident/keep/completion at consumption. There is no future routing prediction, global cache or new kernel.

R2 is a **new numerical profile** relative to R0: attention and router see span153. Its reference is independent of generated answers/drafts and depends only on official inputs, positions and frozen shape. FFN numerical tiles remain32/25. Cross-profile logits/text equality is not inherited. This unit establishes same-profile fidelity, not general quality, first-final, full8K or M4.

## REPRODUZIDO_MODEL_FREE

Actual production helper builds five-consumer dependencies; model-free graph construction verifies shapes, 38/8 wave callbacks and omitted-consumer counterproof without weights or forwards. Directed Python gates reject empty/omitted/duplicated stage sets, missing witness, stale generation, wrong bias component and disagreement with authoritative expert unions. Compilation failures and repairs are preserved. A cache change disabling CUDA/C47 was detected before model execution; explicit configuration is required and frozen. No prior binary hash is inherited.

## Prospective physical gate

New live inventory admits a cap maximum of23GiB. Freeze a common20GiB cap/high for instrumentation, swap0 and preventive cap-minus512MiB stop. The estimate retains the entire prior measured C258 peak16,743,944,192B (including its head), then adds bounded capture pages, graph metadata, reader scratch and2GiB workspace/transient uncertainty. No RSS+file addition or subtraction of peaks from different instants. Estimate is admission only; the first forward demonstrates actual workspace capacity.

Three new processes: unchanged R0 capture189+32 and bitwise comparison with immutable C127 ON; then R2-tile and R2-reuse warm2044 plus153 and six published teacher-forced continuation IDs. Each has its own60s inventory/freshness≤3s at Popen, guarded240s execution and30s post gate. Total envelope1100s; raw projection700MiB; whole epoch/reserve admission required. Fresh roots, same weights/P12/slots40/ub32/context8192/fullSWA/F16/preload/workers/threads and GOMP unset. Only R2 arms have explicit layer-span153.

Capture all216 whole-layer stage payloads, authoritative routes/weights, selected canonical six-component bytes on CPU0/12/24 and GPU25/35, complete drained initial expert state, seven full finite logits. R2-tile versus R2-reuse requires bitwise equality; no epsilon. The R0 bridge permits reuse of the36 original FFN references only where shapes/devices/arithmetic and captured outputs are unchanged. New32/25 whole-span boundaries require their own selected native/canonical references before timing promotion.

Any mismatch, byte/lifetime/read error, nonfinite, identity/evidence/resource failure ends this unit. Preserve partial raw, local receipt and NOT_RUN arms. Repair only an identified cause under a new identity. Captures are NOT production timings. Subsequent service/utility and functional gates remain conditional and are NOT_RUN at freeze.

## Next gate

If fidelity passes, qualify the independent whole-span router and selected native same-device FFN32/25 references, then measure production paths against the operational R0 under equal admitted memory and known initial expert state. Do not use a deliberately slow R2 reference as the product baseline. No opt-in/default promotion from this numerical unit.
