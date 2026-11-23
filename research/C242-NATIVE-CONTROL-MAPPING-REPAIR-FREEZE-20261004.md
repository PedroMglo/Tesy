# C242 — repair last-output API mapping, preserve C241

C241 FAIL_UNIT_PRESERVED: the first control completed its first prefill call,
then queried native input-position index0 even though only its last position
requested logits. No continuation was generated; other classes NOT_RUN.
Full failed receipt, output/error and resource samples remain unchanged.
This is a concrete C-API client defect, not numeric corruption or NO_GO.

SOURCE_AUDITED: `llama_context::output_resolve_row` distinguishes nonnegative
input-position IDs from negative compact output indices. Last-only warmup
uses-1; all-row B verification uses0..B-1. The minimal repair changes that
client mapping only. Backend/graph/weights/libraries and all workloads/caps
are unchanged. The failed binary remains; the fixed helper has a new hash.
Continuation cardinality/official IDs are also validated before weights,
with exactly B required for a grid reference and32 for a controlled loop.

REPRODUZIDO_MODEL_FREE:12 directed native admission/grid/acceptance tests
pass. The native helper self-test exercises the exact mapping function without
loading a model; invalid compact indices fail. Existing-root/mode/IDs/shapes
continue to reject before weights. No dummy model or fake guard is used.

C242 is a new physical family, authorized by the post-C235 identified-repair
rule. It repeats no successful control or performance comparison. Same three
prospective cases, cap128 diagnostic native greedy,240s process deadlines,
60s own inventories,16.75GiB common cap,1080s family,32MiB projected raw.
No head, sampling claim, natural utility qualification or threshold change.
LOCAL_ONLY; budget remains the original C236 epoch.
