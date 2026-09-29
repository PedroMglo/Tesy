# C130b — slots40 original quality12 result

**Result: `PASS_QUALITY_12_OF_12` in the frozen C40 suite.** All twelve
requests ended naturally, and all four code, four SQL and four planning
validators passed. Independent revalidation of raw, resource receipt,
inventory-at-launch and the twelve graders passed. Every official prompt
token array and every full assistant message was exactly equal to both the
historical C40 P12 control and C126 C75/slots32 outputs on these tasks.
This is a strong no-observed-loss result for the frozen tasks, not a claim
about general quality or every context position.

The server completed in 1968.549 s; the live inventory/launch/validation
envelope was2031.314 s. Peak cgroup was15,868,805,120 bytes, total GPU
use6866 MiB, CPU71.25 °C, GPU56 °C, NVMe58.85 °C and workload swap zero.
No stop occurred. The median first final across tasks was110.508 s; C40's
older timing is descriptive only because it is from a different day/regime.

Measurement commit: `80ca50e6f484c66ba1d5e90122c831604ba5f728`.
Raw server SHA256:
`d6c49783dd5c8527664450d22971018800ab7e2e963d2f248ef4eeaabb017e09`.
All raw files remain local, with hashes in `manifest.json`. The effective
C130 premodel cadence failure remains preserved under its own ID; it did
not run the model and is not relabelled as a quality test.

The epoch checkpoint charges11,854.754 s physical conservatively,
leaving at least16,945.246 s physical and24,444.974 s wall at its
timestamp. The confirmed slots40 server still misses M4 on warm first
final and decode. A new eight-task holdout and diverse/active session
remain to be tested before broader recommendation; independent full 8K
attention/KV validation is also `NOT_RUN`. No default or remote write.
