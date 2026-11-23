# C82 — E18 repeat not admitted

- Objective/base: recheck E18 availability for a fresh full-boundary repeat after C78's E16 stop and C79's 256 MiB shortfall. Base Tesy `5056e25` and C75 backend unchanged. Evidence class MEDIDO_NO_TARGET for the model-free 60-second physical inventory.
- Alternative: increased MemAvailable could admit E18. The fresh cap_max was 18,790,481,920 B, 512 MiB below E18. No model or run was started. The NVIDIA dynamic T.Limit-derived stop moved from 89 to 90 C across snapshots while reported relative specifications remained the same; a future comparison must freeze a single guard and report that scope.
- Decision: CAPACITY_NOT_ADMITTED. Do not repeat administrative preflights without material headroom change; continue source/model-free decode cost and residency work. C78 resource FAIL, C76b/C77 PASSs and C81 inference retain their original scopes. No default or remote change.
