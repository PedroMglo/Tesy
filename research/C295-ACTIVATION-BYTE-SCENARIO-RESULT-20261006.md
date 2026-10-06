# C295: two-layer lead admits a movement estimator, not a delivered speedup

ESTIMADO / OPTIMISTIC_OFFLINE_SCENARIO using C294's current original R0 service and missing-demand generations:

| Point | Nominal median | Code median | Sensitivity across both cases |
|---|---:|---:|---:|
| Same CPU layer pre-attention |4.396%|4.436%|3.68–5.39%|
| Two CPU layers earlier, same token |29.404%|33.529%|28.92–34.16%|

These are decode scenario reductions versus the same fixed-service demand-only replay, not observed end-to-end speedups. Four workers, nonpreemptible reads, priority demands,128MiB staging including running/ready, true-demand destination copies, all36layers/32calls and dynamically accelerated feature releases are accounted. Original demand-only replay differs from measured decode by−0.37…−0.32% at service scale1. Altering service scale0.8/1.2 deliberately changes its baseline; those are sensitivities, not calibration failures.

Predictor/false positives are idealized zero; cache demand stream/services/compute are held fixed, no extra hits or physical NVMe bytes awarded. IO/cache/CPU contention and residency can change in a real predictor. This is not FORMAL or a universal roofline. Same-layer window fails the20% investment gate under these assumptions. Two-layer window passes in both cases even across sensitivity: GO_TWO_LAYER_ACTIVATION_ESTIMATOR_INVESTMENT. Next: original destination norm/gate/bias applied to an earlier raw CPU residual; real absent-demand precision/recall, wasted bytes and measured cost; then heldout>=10%netdecode before staging integration. No training/staging/preset/M4 gain yet.

SOURCE_AUDITED current CUDA still computes parked pairs. The deliberately broader current GPU nonwait scope, including CPU24FFN, all GPU attention/FFN/copies/dispatch/logits after subtracting unioned readiness waits, is4.90–4.95%nominal and3.13–3.14%code prefill. Under fixed observed service/dependency assumptions even this gross scope is below15%; no new CUDA operator investment is justified here. It is not a kernel timing or a universal exclusion. D's implementation remains NOT_RUN; reconsider only if the measured critical regime changes under an admitted survivor.

No physical work was added by C295. Raw integrity/hash inputs, queue tests (including preserved fixture failures/correction), assumptions and absolute replay values are in its protocol/scenario/compact. A remainsC286NO_GO and B remainsC293NO_GO; modest transport gains are preserved, not promoted/composed. Continue C autonomously. LOCAL_ONLY.
