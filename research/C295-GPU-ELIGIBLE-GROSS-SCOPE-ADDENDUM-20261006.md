# Current prefill GPU scope, using the same bounded evidence

SOURCE_AUDITED: current pinned mmid/mmq constructs ids_src1/ids_dst/expert_bounds for all selected-and-parked wave pairs, quantizes the full flattened pair count and launches native MMQ. The C47 sentinel/skip is CPU-only. D remains conditional and no CUDA operator is implemented.

The C294 CPU24 pre-attention feature to the next tile's CPU0 feature (or final call endpoint) contains CPU24 FFN plus every GPU layer's attention/FFN, dispatch/copies and final logits. Removing the measured union of CPU24/GPU readiness waits leaves a deliberately generous current nonwait cost scope. This is NOT first-MMID duration and NOT a physical universal bound: observed services and dependency geometry are held fixed. Actual parked-pair kernel work is only part of this scope. Multiple concurrent waits are never summed.

Five153-prefill tiles are mandatory, complete wait endpoints are mandatory, and seven queue/interval tests passed. D's investment threshold remains15% prefill. If even this larger conditional current scope is below15%, no new GPU operator is justified on these inputs; otherwise obtain the narrower missing operator timing before changing CUDA. No old NsightP8/wave-count proxy or 5090 speed is used. This extension changes neither the two forecast points nor any C predicate; no physical run or numeric kernel was added.
