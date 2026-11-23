# C89: further owned tmpfs relocation

- **Objective/base:** obtain a less fragile host-memory start margin after C88. Freeze `b17df508a9e1270bc2a872cd36d628b18f1795a7`; C88 method reused prospectively.
- **Evidence:** two checksum-verified build archives and original-path symlinks in `receipt.json`. Immediate `MemAvailable` rose 733,605,888 B to 22,313,390,080 B, 838,553,600 B above the E18 necessary 20 GiB threshold. **MEDIDO_NO_TARGET** for the snapshot only; concurrent host variation remains possible.
- **Alternatives:** stopping optional user services would offer a smaller, less predictable gain and could disrupt the owner. No process was stopped.
- **Decision:** preserve C48/C54 build outputs on NVMe and run one fresh 60-second E18 capacity preflight. C48 remains `FAIL_SAME_PROFILE_FIDELITY`; C54 remains interrupted. M3 bridge and model run **NOT_RUN**.
- **Tests/limits:** rsync checksum comparison and post-link CUDA library SHA256 passed. This does not prove the 120B will fit through forward or that cgroup file charge will remain low.
