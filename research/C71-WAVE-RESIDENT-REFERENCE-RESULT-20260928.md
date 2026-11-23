# C71 resident canonical FFN reference

Objective: independently recompute routed FFN on the canonical resident CPU/GPU device for every C70 wave-ON activation. Measurement commits `c9244c9394ebc56b828f3683ebcca64a257d3959` and `437b233245158850c0670786c88bb61e6f230b88`. Evidence class: MEDIDO_NO_TARGET. Alternative: OFF/ON streaming equality hides a common routed FFN error.

Boundary witnesses 25–28,24,29 passed, then the other 30 layers passed. Total 36 loads, 250 numeric rows with ordered routing IDs, weights and FFN bitwise; two masked states. No resource stop. This covers the observed routed FFN, not independent attention/KV or universal model correctness. Historical C48/C61/C66 FAILs remain. ON repetition, timing and quality are NOT_RUN. Next discriminating gate: fresh-process ON full-boundary repetition. Raw SHA inventory and maxima are in `results/c71-wave-reference-20260928T1659Z/manifest.json` and `decision.json`.
