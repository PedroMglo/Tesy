# C268 — controlled R0/R2 cost: NO_GO

MEDIDO_NO_TARGET, measurement e9f2c01: four fresh valid ABBA processes,721.340842028s whole physical envelope. Common20GiB/high=max/swap0, own60s inventory, original2044 prefix/call plan and complete drained initial state equal. All native receipts/logits finite, no hardware/resource failure. Official2197inputs and32teacher-forced calls, not free outputs.

| arm | profile | prefix2044 s | prefill153 s | decode32 s | total s |
|---|---|---:|---:|---:|---:|
|1|R0|93.673884149|11.918557880|10.307552406|22.226110286|
|2|R2 shared|93.991222622|8.701745137|11.052448362|19.754193499|
|3|R2 shared|94.364394011|8.282252528|11.110163276|19.392415804|
|4|R0|93.682794217|11.891302025|9.801597028|21.692899053|

Paired prefill gains26.9899494%/30.3503308%, median28.6701401%. Decode gains−7.2267006%/−13.3505412%, median−10.2886209% FAIL protection−5%. Preparation median−0.5331654%, total median10.8632276%. Loads by completed generations CPU/GPU1486/638 in each A versus1441/587 in each B. One of33 native argmax rows differs(index13:5880→10731) in both pairs; cross-profile logits differ. No R0 greedy equivalence claim. This is NO_GO_CONTROLLED_WARM153_NATIVE_COST, not timing noise censored or a hardware FAIL. Utility/confirmation of this exact identity are NOT_RUN_COST_PROTECTION_GATE.

SOURCE_AUDITED: collective-wave ordering is first-use over the entire153-token span. Consequently the final resident set need not retain the last tile's working set. Existing C265 equal-numerical-profile captures show last-four-token expert hits in CPU0 12→8, CPU12 12→11, CPU24 9→5 and GPU25 11→7 when switching tile-major to shared first-use ordering. These are observed historical postprefill states, not a new run or a predictor. C268 non-wave remap stall deltas8.187976/7.707423s in A and8.985975/9.032658s in B accompany the decode regression. Source separates non-wave remap wait from prefill wave wait; neither counter is freely removable latency or physical traffic. Causal attribution remains HIPÓTESE because R0/R2 attention/router differ too.

A bounded repair is justified for investigation: order only the currently authoritative whole-layer expert union by last-use tile, retaining first-use order within that last tile. Each expert still loads once for all its tile consumers; no next-token routes, prediction, added slots or cache. Same per-token arithmetic and six-component byte/lifetime contract must pass bitwise against R2 before any timing. Use new private backend/build identity; preserve C262/C268. A prospective new cost screen keeps the same gates and inputs. If the mechanism fails correctness or fails the decode protection again without another concretely supported repair, close this implementation rather than retune flags. No original opt-in/default/service change; LOCAL_ONLY.
