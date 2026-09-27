# C10b native ub64 ledger

- New identity after C10 two no-model start-precondition blocks. Same ub64 server profile and E18; CPU start threshold is 55 C to tolerate observed idle transients, absolute CPU guard 95 C unchanged. C9 513-ID thermal FAIL remains preserved.
- Freeze init-only→minimum forward→513-ID diagnostic, each with clean measurement commit and no automatic retry. Numeric/reference and quality claims NOT_RUN.
- `c10b-g1-init`, measurement `8093999a871bf8c210298b79f1bb32fc0ff979c0`: PASS init-only, ready/elapsed 4.602 s; peak RSS 4.816 GB, cgroup 5.321 GB, GPU total 3884 MiB, CPU 53.375 C, zero swap. Forward workspace remains unmeasured.
