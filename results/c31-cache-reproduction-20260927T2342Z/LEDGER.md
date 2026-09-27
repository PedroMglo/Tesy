# C31 finite cache-miss reproduction

- C29 two-turn cache_n35 FAIL remains; C30 d1/d2 source-logged cache hits2036 did not reproduce it. C31 freezes three maximum fresh processes with the same source diagnostic logging. Later runs require all earlier cache gates PASS; first actionable miss stops the unit. Three hits end the diagnostic as incomplete, with no further retry here.
- Same original model/backend/binary and two-turn synthetic P12 8K profile, E18 zero swap and CPU100/other guards. Logging only changes observation; timing is diagnostic. Fresh preflight `READY_FOR_IDLE_ADMISSION` on AC/performance CPU48/GPU45/NVMe38.85 C. Focused model-free tests 41 PASS; three protocol hashes checked. C15 source-only, default unchanged.
