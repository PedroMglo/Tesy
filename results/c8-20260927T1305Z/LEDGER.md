# C8 ledger

- Hypothesis: native next-wave preload on P8, only LLAMA_MOE_STREAM_NO_PRELOAD absent versus =1. Numeric189+32 OFF1/ON capture/OFF2, then canonical36 before timing. Original backend/model and E18 unchanged. Historical C4 long OFF/ON logits passed bitwise, but old timing/resource claims remain diagnostic; C8 is prospective.
- Measurement: NOT_RUN. Next: model-free tests/build and clean commit, then bounded numeric preflight.

- G2 observer measurement commit `099e5ecad0975ce49597e80c072e2f5c5a71a057`; `c8-g2-off1`, `c8-g2-on`, `c8-g2-off2` completed under E18. `boundary-summary.json`: SAME_PROFILE_PASS, five full logits bitwise OFF/ON/OFF2 and 33 full logits bitwise OFF1/OFF2. 250 numeric states, 2 masked, 3675 indexed tensors, 1008 equal byte slices; ON issued 3507 preloads, OFF issued 0.
- ON capture peak GPU 3906 MiB, RSS 14,939,480,064 B, cgroup 17,060,282,368 B, CPU 92.25 C, NVMe 54.85 C, swap 0. Initial cgroup estimate was exceeded by capture/page-cache usage; reserve 16.5 GiB was respected. Capture timings excluded. Next: SHA-seal capture raw and run 36 canonical P8 layers with the frozen numerical schema.
- Post-run `c8_seal_capture.py seal` and `verify` both passed for 3686 capture files, aggregate SHA256 `e74a136d71dec1815a7702e8f4057a624e324271e5fba7e1adbedf3839b4642f`. This is a post-run seal, not capture-time proof. Next: freeze reference commit and run witness layers first.

- Canonical witness measurement commit `4adc15be89a76965451e104cdefce1c37c47e917`; layers 25–28, 0, 29, 35 all PASS, 47 numeric bitwise rows and 2 explicit masked. Short reference processes had start/end identity/resource samples, no sustained telemetry claim. Capture SHA seal passed before and after. Next: 29 remaining layers under a new clean measurement commit.

- Remaining reference measurement commit `f70381b94a1e946988763cbfb9ade04c78176bc4`; all 29 loads PASS, adding 203 numeric bitwise states. Combined 36 loads/250 numeric bitwise/2 masked, capture SHA seal unchanged. Reference peak GPU 1754 MiB, RSS 2,345,295,872 B, cgroup 4,020,232,192 B, CPU 62.75 C, swap 0. Next: freeze uninstrumented paired timing runner/gate and test 113 then 496.

- G3 timing measurement commit `6b5dabd4357145a1385bc16784a4ecbb78c9941d`; `c8-g3-pair1-off`, `pair1-on`, `pair2-on`, `pair2-off` passed full 33-row bitwise logits versus contemporary P8 control and all resource gates. Paired medians: prefill +12.44%, T_work +10.24%, TPOT +1.00%; work pairs +8.95%, +11.53%. This short screen does not decide the medium claim.
- Resource peak GPU 3898 MiB, RSS 14,956,146,688 B, cgroup 15,380,504,576 B, CPU 88.625 C, swap 0. ON issued 2936 preloads per run; source ready-on-arrival is not a true preload-hit count. Next: two new alternating 496+32 pairs under the frozen protocol.

- G4 screen measurement commit `77d7ba869797e31731daed995ee4373c2f63d5cb`; `c8-g4-pair1-off`, `pair1-on`, `pair2-on`, `pair2-off` passed full 33-row bitwise logits versus contemporary P8 control and all resource gates. Paired medians: prefill +17.71%, T_work +16.88%, TPOT +4.43%; work pairs +17.11%, +16.65%. `SCREEN496_GO` is a screening decision, not confirmation.
- Screen resource peak GPU 3900 MiB, RSS 14,963,060,736 B, cgroup 14,757,126,144 B, CPU 93.125 C, swap 0. ON issued 7749 preloads per run. Next: three new 496+32 confirmation pairs under the frozen policy, with thermal and resource preflights.

- G5 confirmation measurement commit `d6fd478ad53e4152e8ce2d16a36eabe073a4dda7`; six new 496+32 arms `c8-g5-pair1-off/on`, `pair2-on/off`, `pair3-off/on` passed full 33-row bitwise logits versus contemporary P8 OFF and all resource gates. Paired median prefill +17.70%, T_work +16.59%, TPOT +0.80%; all work pairs positive (+16.13%, +16.59%, +17.11%). `CONFIRM496_GO` applies only to this probe scope.
- Confirmation resource peak GPU 3900 MiB, RSS 14,963,195,904 B, cgroup 14,781,255,680 B, CPU 93.25 C, swap 0. Source wave stall remains diagnostic. Next: separately freeze a 1522+32 check, then serving/session/quality gates; no default change.

- G6 long check measurement commit `a4c8b1c8f07967fa844bd29ba1baa93b8f79f658`; new arms `c8-g6-pair1-off/on`, `pair2-on/off` all passed 33 full-logit bitwise and resource gates. Paired median prefill +18.07%, T_work +17.55%, TPOT −3.63%; T_work pairs +17.77%, +17.32%. `LONG1522_CHECK_PASS` is two-pair length coverage, not independent specialized confirmation.
- Peak GPU total 3900 MiB, RSS 14,956,863,488 B, cgroup 14,767,091,712 B, CPU 93.875 C, swap zero. `/proc/PID/io` and global NVMe counters remain accounting/diagnostic. Next: separate 8K server admission and exact-prefix bridge; default unchanged.
