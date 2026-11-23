# C63 P14 observer boundary result

- Objective/base: first same-profile numerical gate for the P14 profile admitted in C62. Measurement commit `d5cbb2a3f43dd137ea0d9a84fc8f9b92c675ff89`; unchanged C35 backend `c3759bad92c0e6f71bb936afea9b0a162fb83f76`.
- Evidence class: `MEDIDO_NO_TARGET` for loader placement, OFF/ON/OFF outputs, payload schema, mapped libraries and guarded resources. Canonical resident reference is `NOT_RUN` in this phase.
- Three fresh processes completed: OFF1 59.437 s, ON 62.989 s, OFF2 59.169 s. All 33 full OFF logits vectors repeated bitwise. The ON capture's five selected complete logits matched OFF bitwise. The capture validates 250 numerical states, 2 explicit masked positions and 1518 byte/lifetime witness rows, including layers 22/23.
- Placement observed in each probe: CPU layers 0–22, CUDA layers 23–35 and output CUDA. GPU total peaks 6680, 6690 and 6680 MiB; CPU peaks 91.625, 91.375 and 91.5 °C. No swap, OOM or resource stop. Captures alter timing and are not performance evidence.
- Alternative/decision: observer or placement could have changed logits or routing; these selected checks did not show that failure. Streaming versus a resident canonical layer has not yet been tested, so P14 is not promoted to a timed candidate. Attention/KV independent reference and distribution preservation are outside this claim.
- Tests: 125 model-free tests passed, and the reused complete C7b 250+2 fixture passed the schema/logits control before the physical freeze. C63's raw capture has 3686 files indexed by a deterministic tree digest; the compact result and raw paths are in the C63 manifest.
- Failures preserved: C48 and C61 unchanged. M3 retains only C52b scope; M4 not met.
- Next gate: canonical resident FFN reference starts with changed layers 23/24 and boundaries 22/25, plus layers 0/35, then all remaining layers. Any wrong routed ID, weight, FFN bit or resource failure ends that reference unit.
