# C90: E18 host capacity after scratch relocation

- **Objective/base:** fresh 60-second capacity gate after C88/C89 preserved own `/tmp` builds on NVMe. Freeze `80882e3e2fcdc7ccf7e7cbcb913ec2db74edf4a7`; no model loaded.
- **Evidence:** 61 target-host samples, maximum gap 1.000405 s; minimum `MemAvailable` 22,293,942,272 B, external variation 467,288,064 B, reserve 2 GiB. Existing policy derives cap max 20,132,659,200 B (18.75 GiB), above requested E18 by 805,306,368 B. Memory PSI full avg10 zero; ancestor cgroups unbounded; AC/performance and CPU/GPU/NVMe sensors present. **MEDIDO_NO_TARGET** model-free.
- **Alternative/limit:** host availability can change before launch; 60-second headroom does not bound model workspace, cgroup file charge, 8K KV or forward. C78's earlier E16 resource FAIL remains valid.
- **Decision:** E18 host capacity admitted for a new bounded init/forward unit; full 8K session bridge and fidelity still **NOT_RUN**. Recheck availability and freeze source/profile/guards before any model run. No service stopped, no default changed.
