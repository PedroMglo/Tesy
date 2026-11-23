# C88 scratch relocation

- Freeze `30532a25d930e647cda24b66e6770a1d84cea0a5`; no 120B run.
- Preserved 2,519,457,669 B of C15/C46/C47 build files from `/tmp` on NVMe using `rsync -aH`, checksum comparison, and original-path symlinks. CUDA library hashes in `receipt.json`; no service was stopped.
- Immediate `MemAvailable`: 20,407,398,400 → 21,545,500,672 B (+1,138,102,272 B). E18 necessary threshold 21,474,836,480 B is exceeded by only 70,664,192 B; 60-second capacity admission remains NOT_RUN.
- Next: separately archive another obsolete owned build set to provide a meaningful start margin, then perform a fresh preflight. C78 FAIL unchanged.
