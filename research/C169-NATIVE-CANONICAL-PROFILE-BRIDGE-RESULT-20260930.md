# C169 incomplete native canonical bridge

MEDIDO_NO_TARGET:117.675974s live. Repaired routing output lifetime yields bitwise ordered IDs/weights/FFN for CPU layers0–23,120rows. Layer24 ordered IDs and weights bitwise at all five phases; FFN not bitwise, maximum abs0.00048828125, allfinite. Stops immediately,11remaininglayers55rows NOT_RUN. Historical FAIL unchanged. No tolerance relaxation. No performance screen accepted.

C166 same-profile five full logits and1080selected states remain bitwise in all modes,canonical expert payloads verified. C169 independent reference does not complete36FFNcoverage. These are separate evidence axes.

SOURCE_AUDITED: native source and captureddevices.tsv confirm dense/router map0–24CPU/25–35CUDA,CPU_Mapped expertweightsall36. At layer24 ffn_moe_out is already CUDA0; activation,router and bias-added expert outputs there are CUDA_Host. Canonical reference for24 instantiates onlyCPU backend,with no downstreamGPUgraph; therefore identical final operator placement/fusion is not demonstrated. Pinned scheduler GPU up/down expansion is different in the fullgraph. Buffer provenance is not a full operation/fusion map. The exact arithmetic source of mismatch remains UNKNOWN; blaming model/quantization or changing thresholds would be unsupported.

The single causal output-lifetime repair was reproduced withoutmodel and passed layers0–23. A further weights retry is not justified by a complete model-free mapping proof. This ends B at an explicit tooling/numeric bridge gate,not a performance NO_GO for upstream/mmap.

Next discriminant: extract the actual FFN node/backend/fusion plan for the mixed boundary24 andGPU layers from the pinned native scheduler,then construct and test the one-layer reference to that plan (including order/views/weighted reduction). Numeric before any prefix/server or timing comparison. Retain observed bitwise contracts. No new reference/profile automatically inherits C75/M4/quality.
