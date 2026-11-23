# C53b model-free cost ledger

- C53 endpoint analyzer FAIL preserved; C53b uses last cumulative counter as a lower bound for the 0.4355 s terminal gap, excluding that row from I/O medians.
- 18 complete incremental 153-ID windows: median `/proc/PID/io read_bytes` 37.21 GiB/request, split 15.52 GiB prefill and 21.62 GiB decode. Prefill/decode medians 25.92/16.29 s.
- No physical model run, causal stall claim or NVMe traffic claim. Warm153 is distinct from C46 cold513.
- Next: C54 source/static feasibility of a same-workload tagged-I/O/MMID diagnostic, with physical budget gate.
