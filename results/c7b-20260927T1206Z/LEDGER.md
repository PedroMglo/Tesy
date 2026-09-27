# C7b ledger

- Measurement commit `505c3ce1cbb5aad3f42d1b312f3d0bfdaa98b551`; original backend `1248fd8...`; P12, ub32, slots32, E18.
- New runs: `c7b-g2-p12-off01`, `c7b-g2-p12-on01`, `c7b-g2-p12-off02`. All returned 0 under guards. Five complete 201088-F32 selected logits vectors were bitwise equal OFF/ON/OFF2. OFF1/OFF2 full 33-row payload hashes also match.
- Capture: 250 numeric states and two explicit masked entries; 3675 indexed tensors, 996 equal canonical-byte slices. Structural summary: `boundary-summary.json`.
- Prior C7 attempt 01 remains `GATE_REPAIR_BLOCKED` after an unobservable aliased stage was required by its validator. One transient read-only `nvidia-smi` query failed after C7b ON; three later queries and the OFF2 preflight passed. Incident raw is preserved.
- Canonical layer replay, P8/P12 timing, session, context and quality: NOT_RUN. Next: layers 25–28, then 24/29, then remaining layers if all bitwise.
