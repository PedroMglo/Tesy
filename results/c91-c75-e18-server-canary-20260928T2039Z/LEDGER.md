# C91 C75 server canary

- Measurement freeze `2d9a72e550a1788fd7e353294f090e3287db2e5e`; frozen backend/model/flags and 8K E18 resource contract checked model-free.
- One attempted launch returned `FAIL_RESOURCES_OR_EVIDENCE` before any raw/model process: `frozen cgroup cap and zero swap not enforced`. Original `decision.json` remains unchanged.
- Diagnosis: the script was launched directly from the unbounded shell cgroup (`memory.max` and `memory.swap.max` both `max`). A separate tiny `systemd-run --user --scope` test applied 18 GiB/zero swap correctly. No model was loaded; numeric and thermal gates NOT_RUN.
- Next: new canary identity with explicit outer scope. No retry under C91.
