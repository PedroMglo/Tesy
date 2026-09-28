# C96 server wave bridge

- Objective: test C75 wave skip in the 8K P12 server profile with actual assistant history and exact prefix reuse. Compare contemporaneous C35 control and C75 candidate in separate fresh processes.
- Base investigation commit: `6c4e05180f00ec02f713b8a621a92ef2f0fc449c`; C75 backend `27d2e42d8c994507ee6d71acc7c58d3eddd3f7a5`; C35 backend `c3759bad92c0e6f71bb936afea9b0a162fb83f76`. Measurement commit will be recorded before execution.
- Evidence so far: C93–C95 bitwise same-profile boundary, 36 resident FFN references and fresh ON repeat; C92 scoped server canary. These do not measure C75 session latency.
- Hypothesis: skip of parked wave pairs remains correct through serving and reduces server work. Alternative: server scheduling, generated-token path, cache behavior or thermal/memory effects erase the probe gain.
- Frozen small test: one C35 run followed by one C75 run, each with two synthetic turns under E18 zero swap, P12/ub32/slots32/preload ON, 8192 context, full SWA/F16 KV, medium effort, seed 42, temperature 0, cap 256. Second turn includes the actual first assistant message. Official token IDs, cache counts, monotonic request markers, stream completion, final content, resource telemetry and mapped libraries are gates. The 1960-word prefix is synthetic; it is not a diverse quality test.
- Primary decision: each arm must pass receipts independently; compare exact token IDs/outputs before attributing latency. This single pair is a bridge and descriptive timing only; performance promotion requires separately frozen alternating screening and fresh confirmation.
- Stop: first identity, output, cache, fidelity, resource, telemetry, timeout or allocation failure closes the affected run; no automatic retry. C48/C78 and other historical FAILs remain unchanged.
- NOT_RUN at freeze: C96 model, performance screening, M3 varied conversation/active sustained load, M4 quality and latency qualification.
- Next discriminating gate if bridge passes: freeze two alternating server pairs on identical exact-prefix inputs and session metrics, or address any observed bridge failure under a new identity.
