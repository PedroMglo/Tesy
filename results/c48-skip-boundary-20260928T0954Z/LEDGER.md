# C48 parked-pair numeric boundary

- New identity after C47 runtime assertion; C47 FAIL preserved.
- Source fix: host-accessible CPU cache test, commit 0bc5c75 in isolated backend.
- OFF, ON, fresh ON captures planned; timing and canonical references remain NOT_RUN pending bitwise gates.

- OFF c48-g2-off01: capture/resource PASS, 71.150 s. ON c48-g2-on01: capture/resource PASS, 58.063 s.
- Pair FAIL: first difference {'phase': 'prefill0', 'layer': 0, 'stage': 'ffn_moe_out', 'flat_f32_index': 11520, 'token_in_chunk': 4, 'feature': 0, 'off_f32': 0.4479004740715027, 'on_f32': 0.08821175992488861}; 1442/1500 core rows and all five full logits differ. Fresh ON, canonical layers and timing NOT_RUN.
- Next: distinct exact-prefix/session gate for M3. C47 and C48 failures retained.
