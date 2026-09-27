# C8 ledger

- Hypothesis: native next-wave preload on P8, only LLAMA_MOE_STREAM_NO_PRELOAD absent versus =1. Numeric189+32 OFF1/ON capture/OFF2, then canonical36 before timing. Original backend/model and E18 unchanged. Historical C4 long OFF/ON logits passed bitwise, but old timing/resource claims remain diagnostic; C8 is prospective.
- Measurement: NOT_RUN. Next: model-free tests/build and clean commit, then bounded numeric preflight.

- G2 observer measurement commit `099e5ecad0975ce49597e80c072e2f5c5a71a057`; `c8-g2-off1`, `c8-g2-on`, `c8-g2-off2` completed under E18. `boundary-summary.json`: SAME_PROFILE_PASS, five full logits bitwise OFF/ON/OFF2 and 33 full logits bitwise OFF1/OFF2. 250 numeric states, 2 masked, 3675 indexed tensors, 1008 equal byte slices; ON issued 3507 preloads, OFF issued 0.
- ON capture peak GPU 3906 MiB, RSS 14,939,480,064 B, cgroup 17,060,282,368 B, CPU 92.25 C, NVMe 54.85 C, swap 0. Initial cgroup estimate was exceeded by capture/page-cache usage; reserve 16.5 GiB was respected. Capture timings excluded. Next: SHA-seal capture raw and run 36 canonical P8 layers with the frozen numerical schema.
