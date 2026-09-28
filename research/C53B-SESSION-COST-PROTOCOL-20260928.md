# C53b — terminal-aware session I/O accounting

- Objective: close the C53 model-free analyzer gap while preserving its failure.
- Base: `7a2a596` on `campaign/120b-session-cost-attribution-20260928-1254utc`; no model run.
- Evidence: C53 attempted to interpolate C52b's final request end 0.4355 s after its last sample and correctly refused to invent a counter. The server's resource gate allowed this terminal gap (<2 s).
- Prospective method: use the last observed cumulative I/O counter as a **lower bound** only for a terminal gap <=2 s. Mark that request clipped and exclude it from I/O medians. Require at least 18 complete incremental windows; all other sample gaps <=3 s.
- Alternative: even large accounted read bytes may overlap CPU work and reveal no exclusive I/O stall. C46's cold513 wave fraction cannot be transported to warm153.
- Tests: three focused terminal/interpolation tests and six assistant-history helper tests passed (9/9). Physical run: NOT_RUN.
- Decision: report process accounting and time fractions as diagnostic, with no speedup or physical NVMe traffic claim. Next gate must isolate the competing wait mechanisms on the same workload before modifying runtime.
