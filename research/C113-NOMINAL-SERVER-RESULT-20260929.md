# C113 — scope repaired, cold match not admitted

Measurement commit `59219176e50ffc0b2f5a29f6a48372025f023192`. The first C35 server arm passed E18 scope and all output/cache/resource gates, with two complete requests, official prompt counts 2043 and 2197, and 2044 cached IDs in the second. CPU peak 95.125 °C was a warning, below the frozen 100 °C stop; GPU peak64 °C, NVMe57.85 °C, workload swap0. The actual assistant reply was retained in the second request.

C75 ON did not start. Its 300 s relative cold matching window ended with NVMe38.85 °C; the C35 start had NVMe33.85 °C, requiring ≤35.85 °C. The candidate receipt remains `FAIL_RESOURCES_OR_EVIDENCE` with the specific matched-start error, zero requests and no model launch. The scientific decision is `INCOMPLETE_MATCH_NOT_ADMITTED`, with no timing pair and no speedup. Pair2 is NOT_RUN. C112's premodel scope FAIL, C100 NO_GO, C109 timeout and C110 matching stop remain unchanged.

This shows the scoped launcher fix worked, and that the first-arm start was too cold for a 300 s NVMe recovery after its full cold request. A prospective operational warm-start family could test the server question without seeking the same cold band; it needs a new identity, temperature band and full budget admission. No default or remote change.
