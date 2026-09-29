# C115 — model-free bound for the observed nominal153 request

Objective: quantify the remaining latency after removing the measured prompt phase from the **single** C114 C75 ON incremental request, holding its decode and other phases fixed. Alternative: prefill alone is enough to reach the prospective ≤10 s first-final goal. Targets 10 s first final and 6 tok/s decode were set before C114 and remain unchanged.

Inputs and hashes are frozen in `results/c115-decode-goal-bound-20260929T1050Z/protocol.json`: C114 raw/manifest/decision, C111 paired timing, C108 corrected trace analysis. The analyzer validates each hash, C114's raw-manifest binding, complete second request with 153 new prompt IDs/2044 cached IDs/47 completion tokens, finite phases, two C111 pairs and C108 trace gate. It then calculates `first_final - prompt_ms/1000` and `100*(1-observed_tps/6)`. No C105 wait is divided by C114 wall time: those workloads and clocks differ, and the trace misses some waits.

This is an inferred, conditional phase subtraction, not a physical intervention or server A/B gain. It neither says zero prompt is feasible nor certifies M4 from one run. Raw stays local; no model execution, remote publication or default change.
