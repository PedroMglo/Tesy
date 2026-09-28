# C88: preserve old builds outside tmpfs

- **Objective/base:** test whether owned scratch, rather than user services, can improve host memory headroom. Freeze `30532a25d930e647cda24b66e6770a1d84cea0a5`; original C15/C46/C47 source and current C75/C84 builds unchanged.
- **Evidence:** `receipt.json` records three verified archive copies, original-path symlinks, library hashes and before/after `/proc/meminfo`. `MemAvailable` rose 1,138,102,272 B, from 20,407,398,400 to 21,545,500,672 B. **MEDIDO_NO_TARGET**, instantaneous only; concurrent host activity is an alternative explanation for part of the change.
- **Decision:** keep the relocated builds on NVMe. The E18 necessary threshold (20 GiB) is exceeded by only 70,664,192 B; a 60-second admission and full-model bridge remain **NOT_RUN**. No services stopped, no model run, no historical FAIL reclassified.
- **Tests/limits:** `rsync -aHcn --delete` showed identical archives; post-link CUDA library SHA256 matched. This did not test server startup, cgroup file charge or 8K workspace.
- **Next discriminating gate:** archive another obsolete owned build set under a new identity, then perform a new 60-second E18 preflight if headroom improves materially.
