# C85 monotonic request markers

- Source freeze `2952b2fbbfff52c0d89b58612db2125d1d9f0f7c`; opt-in markers added to the existing bounded server runner. Historical protocols have the flag absent.
- A separate no-replace `.request-markers.jsonl` records request start and completed response in host `CLOCK_MONOTONIC` nanoseconds. An interrupted request leaves its unmatched start for explicit `INCOMPLETE_EVIDENCE` classification.
- The focused and mocked-entrypoint suite passed 52/52. Missing contract, non-bool flag, duplicate/overlapping windows, wrong raw receipt and invalid JSON fail their gates. No model was loaded.
- Client windows do not independently mark server prefill/decode. C84 `n_tokens` and a frozen call plan must validate phase attribution before any trace analysis.
- Next: capacity-admitted C75 8K numeric bridge; then one C84 instrumented warm153 diagnostic with these markers, separate neutral timing bridge. C48/C61/C66/C78 remain FAIL and C79/C82 remain non-admitted. No default or remote change.
