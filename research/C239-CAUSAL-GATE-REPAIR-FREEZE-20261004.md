# C239 — correct observer postgate; continue untested shapes

C238 remains **FAIL_UNIT_PRESERVED**. Its sole B2 process completed and
measured fixed-shape masked-future independence and clean rollback bitwise;
R0 versus B2 full logits differ in both rows, with both argmaxes equal.
The postgate then incorrectly required `ffn_moe_logits_biased` in every state.
Historical C7 declares that stage OPTIONAL; the preserved C127 raw and current
C238 raw do not expose it. No backend, consumer witness or payload changed.

REPRODUZIDO_MODEL_FREE: repair requires all seven actual graph stages and
allows only that optional stage. Missing/duplicate/state-count payloads and
truncated consumer witness remain rejected. Seven directed tests pass.
Reanalysis of immutable B2 raw:180 layer states,732 consumer components,
eight complete logit rows over five phases; raw tree
`0bee3a4677c62b1a400f20918d610ba4a3bd0fba6196feee1983a1ec7bf208f2`.
This separate reanalysis does not rewrite the historical failed receipt.

C239 physically runs only previously NOT_RUN B4/B8, in that order. No B2
replacement. The native probe and libraries remain identical. Prospective
cap16.75GiB, inventories60s,240s native deadline/45s gate,720s envelope,
512MiB projected raw, otherwise exactly C238. First negative/invalid run
stops the unit; all raw are preserved. Independent R1 and canonical new-shape
references remain unqualified; no timing/head promotion.

No previous epoch is reopened or budget transferred. LOCAL_ONLY.
