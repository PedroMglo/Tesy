# C8 ledger

- Hypothesis: native next-wave preload on P8, only LLAMA_MOE_STREAM_NO_PRELOAD absent versus =1. Numeric189+32 OFF1/ON capture/OFF2, then canonical36 before timing. Original backend/model and E18 unchanged. Historical C4 long OFF/ON logits passed bitwise, but old timing/resource claims remain diagnostic; C8 is prospective.
- Measurement: NOT_RUN. Next: model-free tests/build and clean commit, then bounded numeric preflight.

- G2 observer measurement commit `099e5ecad0975ce49597e80c072e2f5c5a71a057`; `c8-g2-off1`, `c8-g2-on`, `c8-g2-off2` completed under E18. `boundary-summary.json`: SAME_PROFILE_PASS, five full logits bitwise OFF/ON/OFF2 and 33 full logits bitwise OFF1/OFF2. 250 numeric states, 2 masked, 3675 indexed tensors, 1008 equal byte slices; ON issued 3507 preloads, OFF issued 0.
- ON capture peak GPU 3906 MiB, RSS 14,939,480,064 B, cgroup 17,060,282,368 B, CPU 92.25 C, NVMe 54.85 C, swap 0. Initial cgroup estimate was exceeded by capture/page-cache usage; reserve 16.5 GiB was respected. Capture timings excluded. Next: SHA-seal capture raw and run 36 canonical P8 layers with the frozen numerical schema.
- Post-run `c8_seal_capture.py seal` and `verify` both passed for 3686 capture files, aggregate SHA256 `e74a136d71dec1815a7702e8f4057a624e324271e5fba7e1adbedf3839b4642f`. This is a post-run seal, not capture-time proof. Next: freeze reference commit and run witness layers first.

- Canonical witness measurement commit `4adc15be89a76965451e104cdefce1c37c47e917`; layers 25–28, 0, 29, 35 all PASS, 47 numeric bitwise rows and 2 explicit masked. Short reference processes had start/end identity/resource samples, no sustained telemetry claim. Capture SHA seal passed before and after. Next: 29 remaining layers under a new clean measurement commit.

- Remaining reference measurement commit `f70381b94a1e946988763cbfb9ade04c78176bc4`; all 29 loads PASS, adding 203 numeric bitwise states. Combined 36 loads/250 numeric bitwise/2 masked, capture SHA seal unchanged. Reference peak GPU 1754 MiB, RSS 2,345,295,872 B, cgroup 4,020,232,192 B, CPU 62.75 C, swap 0. Next: freeze uninstrumented paired timing runner/gate and test 113 then 496.
