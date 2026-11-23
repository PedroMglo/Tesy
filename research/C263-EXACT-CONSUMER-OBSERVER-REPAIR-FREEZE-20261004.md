# C263 — exact native consumer observation

C262 remains `FAIL_UNIT_PRESERVED`: its unchanged R0 bridge passed1500 core payloads/five logits and the prospective witness; R2-tile exited with `consumer is not a native remap op`, and R2-reuse was NOT_RUN. GPU13MiB and inactive own scope were observed after cleanup. No performance or numeric corruption conclusion follows from this observer failure.

SOURCE_AUDITED cause: `std::stoi` accepted a layer number followed by scheduler-generated `(view)`/`(cont)` annotations. The observer mistakenly treated derived tensors as original remap consumers and also captured derived stage aliases. The correction requires the full exact native `stage-layer` name. All byte, slot/generation/lifetime/type/stage/finite checks remain.

REPRODUZIDO_MODEL_FREE: the actual C262 production graph helper and callback are used to test original consumer selection, rejection of its derived view and contiguous copy, all five lifetime dependencies and the missing-consumer counterproof. No weights/forwards. Source repair is observer-only; private backend commit93151fc4 and its final CUDA/C47 library set are unchanged. Original failed binary and all partial raw are retained with SHA/size manifest. Existing R0 bridge is reused within its selected scope; no36-reference repeat.

Prospective new root/identity, separate corrected binary, two new R2-tile/shared captures, same original official inputs,153/32/25 shape, medium/ctx8192/P12/slots40/KV/preload/threads/workers/GOMPunset. Same20GiB instrumentation cap/high, cap-minus512MiB preventive stop, swap0 and frozen live policy. Each own60s inventory/freshness3s,240s bounded execution,30s post gate; family740s, raw projection600MiB. The unchanged whole-layer bitwise gate and independent canonical reference requirement remain. No new timing, quality, first-final or M4 claim.

Any new execution failure ends this unit; preserve it and diagnose a concrete cause under the existing epoch. No repetition to select favorable outputs. LOCAL_ONLY. C263 is a permitted observer repair, not a changed numerical target or a relaxed threshold.
