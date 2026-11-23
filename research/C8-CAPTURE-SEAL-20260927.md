# C8 capture post-run seal

- Objective/base: make the C8 observer raw read-back verifiable before canonical replay. The capture originated in measurement commit `099e5ecad0975ce49597e80c072e2f5c5a71a057`; the seal tool was committed in `76f854bb3bcb3dc921251c7346be6ab72e34a998`. Original backend/model and physical outputs were not rerun.
- Evidence class: post-run SHA inventory over all 3686 files in `results/c8-20260927T1305Z/raw/c8-g2-on.capture/`, after the capture schema/byte gate passed. Aggregate SHA256 is `e74a136d71dec1815a7702e8f4057a624e324271e5fba7e1adbedf3839b4642f`. A separate verification reread every file and passed. This does not prove hashes were sealed at callback time.
- Decision: reference runner must validate this inventory before and after its canonical layer sequence. A missing or changed raw file blocks new reference claims. No model execution or performance timing occurred in this sealing step.
- Tests: 59 focused model-free tests passed, including a changed-raw-inventory mutant and missing-seal mutant. Canonical36, paired timing, server, functional tasks, 8K and sustained session: NOT_RUN.
