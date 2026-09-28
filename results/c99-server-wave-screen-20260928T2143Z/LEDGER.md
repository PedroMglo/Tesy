# C99 ledger

- Code `52f31ce`, protocol/measurement `3b0d9e6`. Model-free tests: 18/18 PASS. Fresh 60 s E18 inventory admitted.
- Runs in order: `c99-p1-control`, `c99-p1-candidate`, `c99-p2-candidate`, `c99-p2-control`, each under `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0`. All 4 PASS, complete 2-turn responses, no swap/OOM/guard stop. Raw hashes: `manifest.json`.
- Matched-start waits: 226.514 s and 9.410 s. Cold prefill gains per pair: 75.508%, 75.361%; median 75.435%. Protected medians all positive. Exact official prompt IDs and assistant messages match in all arms.
- State: `SCREEN_GO_CONFIRMATION_PENDING`. Two pairs are screening only; no diverse quality, p95 or M4 claim. Historical C48/C78 and C96/C97 prelaunch FAILs remain.
- Next: three new alternating server pairs on the frozen profile/workload, then diverse session and utility qualification if confirmed.
