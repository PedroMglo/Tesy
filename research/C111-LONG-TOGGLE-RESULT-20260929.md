# C111 — same-binary long OFF/ON toggle

Objective/base: C75 flag effect under the 2009+192 P12/8K teacher-forced call plan, with operational matched starts. Measurement commit `2be6662c21e29d43b7269076b57d6779fdffec10`; protocol and input hashes in `results/c111-long-toggle-20260929T0930Z/protocol.json`. This new unit follows C110's cold matching stop and does not change its result.

Measured on target: three canaries and four full arms passed. Each long arm produced 193 complete 201088-F32 logits rows bitwise equal to the C110 B reference; swap/OOM and resource guards passed. Both pairs are fresh-process and order reversed.

| Pair | Order | Prefill OFF→ON (s) | Full decode OFF→ON (s) | Late 65–192 OFF→ON (s) |
|---|---|---:|---:|---:|
| 1 | B→C | 508.176→337.172 (+33.65%) | 47.207→50.431 (−6.83%) | 27.891→29.165 (−4.57%) |
| 2 | C→B | 534.609→333.233 (+37.67%) | 49.395→48.880 (+1.04%) | 29.187→27.923 (+4.33%) |

The median of paired gains is +35.66% prefill, −2.89% full decode and −0.12% late decode. The initial 1–64 decode window regressed −10.09% and −3.71% in the two pairs (median −6.90%). Thus the frozen criterion finds **no persistent >5% late decode penalty** from ON in this probe, while early decode has a consistent negative sign. The full-decode sign changes with order. Two pairs do not establish a robust distribution or explain C100's confirmed server decode regression. C100 remains `NO_GO_CONFIRM`; C104 remains a separate short diagnostic.

Interpretation: waves is a faithful prefill mechanism in this tested same-profile scope and substantially improves this synthetic long prefill. It is not a promoted general server profile: the product workload is free generation, nominal128 actual-history increment and first-final timing, not 192 forced IDs. The next discriminant is a bounded server bridge using that workload, with decode and first-final protections. No attention/KV independent reference or broad M4 quality claim arises from C111.

Evidence: `runs.jsonl`, `timing-pairs.json`, `resource-summary.json`, `decision.json` and local raw hashes in `manifest.json`. C109 `FAIL_TIMEOUT` and C110 `INCOMPLETE_ATTRIBUTION_MATCH_NOT_ADMITTED` stay intact. No default or remote change.
