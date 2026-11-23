# C79 — E18 admission after C78

- Objective/base: determine whether a fresh E18 cgroup cap can safely support a new full-boundary repeat after C78's E16 preventive stop. Base Tesy `9fed024` (full SHA recorded by Git); backend C75 unchanged. Evidence class MEDIDO_NO_TARGET for a 60-second model-free physical inventory; no inference.
- Alternative: the C78 file charge was specific to E16 and an admitted E18 scope could finish. C79 measured cap_max 19,058,917,376 B, 256 MiB below E18 19,327,352,832 B. A smaller cap was not selected because C78's file charge was still rising at the guard and lacked a conservative forward bound.
- Decision: CAPACITY_NOT_ADMITTED, no model loaded. C78 resource FAIL and C76b/C77 numeric PASSs remain unchanged. Next discriminant: prepare the 8192-context session gate model-free, then recheck host admission under a new identity when capacity improves. No remote/default change.
