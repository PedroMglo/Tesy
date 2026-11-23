# C109 ledger

- Protocol frozen before inference: C35/C75 OFF/C75 ON; 2009+192 official IDs; P12/8K/E18/slots32/ub32/preload ON. Source and binaries are original preserved backends. Nine-arm order and stops are in `protocol.json`.
- Model-free: 22 relevant tests PASS; both backend tokenizers agree bytewise; malformed ID fixture rejected. Fresh 60-second host inventory derived E18 policy and GPU temperature stop 89 °C. A vocab-only CUDA visibility check outside the tool sandbox found one device.
- Physical: canaries A/B/C passed, with identical hashes of all three full-logit rows. The first long arm, `c109-b1-a` (C35), hit its frozen 450 s timeout at 451.144 s. No 192-step output or timing pair exists. The runner stopped; later arms are NOT_RUN. Maximum observed CPU/GPU/NVMe was 91.625/58/56.85 °C, cgroup peak 13,026,258,944 B, swap and OOM events zero. This is `FAIL_TIMEOUT`, not a thermal failure.
- `decision.json` and `manifest.json` bind the raw. The scope ended and no campaign model process remained. C100 NO_GO and C104 diagnostic remain unchanged. Raw, binaries and prompt text remain local outside Git.
