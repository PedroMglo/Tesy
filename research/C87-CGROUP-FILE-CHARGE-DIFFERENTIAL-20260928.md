# C87: cgroup file charge differential

- **Objective and base:** explain the C78 preventive memory stop using preserved C76b/C78 telemetry. Source/protocol freeze `8f2cdcab8340c1ad4ae0dd7dc628cb5658b412ec`; both parents retain their original decisions.
- **Evidence:** hash-verified raw sample streams and parent protocols. At a matched 14 s, C78's `memory.current` exceeded C76b by 2,502,569,984 B, and `memory.stat file` by 2,498,019,328 B. `anon` differed by −12,288 B; RSS by +208,896 B. C78's incomplete capture was 25,912,848 B. Class: **INFERIDO** for attribution to the aggregate `file` counter, not an inode or allocator.
- **Alternative:** page cache, another file-backed charge, or different reclaim behavior under the E16 versus E18 scopes. The existing counters do not distinguish these. An exact cause remains **DESCONHECIDO**.
- **Decision:** preserve C78 `FAIL_RESOURCES_OR_EVIDENCE`; do not relax its guard or call C76b/C78 a controlled A/B for cache causality. M3 bridge remains **NOT_RUN** for capacity admission. Model runs: zero.
- **Tests:** three directed tests passed, including parent control, hash mismatch and profile mismatch. New model/physical telemetry **NOT_RUN**.
- **Next discriminating gate:** examine owned scratch/build memory and host headroom, then run a new 60-second admission only after a material change. A future model run would need per-inode/file-cache attribution if this differential recurs.
