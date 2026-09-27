# C14 P12/ub64 8K server ledger

- New numeric profile after C11 P12/ub32 513 completed at CPU95 and C13 P12/ub32 first513 failed CPU95.125. Only ub32→64 relative to C11.
- Freeze init-only→78-ID forward→513-ID cold diagnostic, each with a clean measurement commit, E18 guards and no retry. Numeric/timing/quality promotion NOT_RUN.
- `c14-g1-init`, measurement `763b22ee2890379f574ed97f7db035c827f7a06d`: PASS init-only, 4.630 s, peak GPU 5702 MiB, RSS 4.955 GB, cgroup 4.732 GB, CPU 48.5 C, zero swap. Forward workspace and per-layer server placement not observed at log level3.
- `c14-g2-forward`, measurement `b4fe6507aed4e47f9bee3fa894b3daea673ed18a`: 78 official prompt IDs + 4 output tokens completed, cache_n=0. Backend prefill 21.989 s/decode 1.043 s, API 23.036 s, scope 27.823 s; peak RSS 13.248 GB, cgroup 13.021 GB, GPU 5716 MiB, CPU 84.25 C, zero swap. One short diagnostic only; 513-ID gate remains.
