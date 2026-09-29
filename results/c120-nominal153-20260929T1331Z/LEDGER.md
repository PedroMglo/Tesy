# C120 nominal153

- New epoch starts `2026-09-29T13:31:15Z`, budget 12 h wall / 8 h physical; previous epoch remains closed. Source commit `6a961a608ad213b5128e87176c25ed44026d9aea`.
- C119 clock-origin defect corrected in `9082415b69d718b88804de072f9ecf14fc10452d`. C120 gates at the actual server `Popen` boundary and stores launch/receipt linkage.
- 23 directed model-free test methods passed. Four IDs reach the real Popen boundary with valid synthetic inventories; missing, swapped, wrong-cap and stale inventories prevent it at each ID.
- Real 60 s host inventory: `snapshot.json` and `resource-policy.json`; E18 admitted. Real E18/zero-swap scope test passed. A harmless HTTP server completed the actual inventory→Popen→monitor→raw path with no stop reason; see `model-free-smoke/result.json`. Model weights were not opened.
- C120 input is byte-identical to C117 `session-input.json` (SHA256 `57cdc0a34842943a4abc0cad852ed2f50adb4fe183aede17f23dff1bcd0a0fed`). New arms are `c120-p1-control`, `c120-p1-candidate`, `c120-p2-candidate`, `c120-p2-control`.
- Physical screen at freeze: `NOT_RUN`. C117 stays `FAIL_RESOURCES_OR_EVIDENCE`; C100 stays `NO_GO_CONFIRM`. No default or service change; no remote publication.
- Next: commit the frozen protocol, then run the four fresh processes in order under E18/zero-swap with a new 60 s inventory immediately before each launch. Stop the family on a failing arm.
