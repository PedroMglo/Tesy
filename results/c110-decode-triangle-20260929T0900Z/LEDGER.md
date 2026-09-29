# C110 ledger

- New identity after C109 `FAIL_TIMEOUT`; C109 raw and decision retained. Only the long-arm timeout changes from 450 to 750 s.
- Protocol and budget frozen before inference; 22 model-free tests passed; copied binaries/inputs hash-match C109. E18 under the fresh 60 s snapshot; three triangular block orders and stop rules in `protocol.json`.
- Physical: three 16+2 canaries PASS with identical full-logit hashes. The first A/C35 and B/C75-OFF long arms PASS; their 193 full-logit rows have identical SHA. A prefill/decode 507.238/49.189 s; B 507.190/48.854 s. B/A late-window gain −0.103% on this one pair.
- The second cold matching wait expired after 300 s aggregate for block 1, with NVMe 39.85 °C versus required ≤38.85 °C. C was not launched; blocks 2–3 are NOT_RUN. Decision `INCOMPLETE_ATTRIBUTION_MATCH_NOT_ADMITTED`, not a thermal guard failure. Original C109 timeout and C100 NO_GO stay unchanged. Raw hashes in `manifest.json`; no remote publication or default change.
