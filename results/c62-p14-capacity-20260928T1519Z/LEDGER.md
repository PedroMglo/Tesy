# C62 ledger

- Measurement commit `36819f62f4127603ae237e939511ab50501eb068`; E18/zero-swap, C35 session backend, command P14/slots32/ub32/n_ctx8192.
- `c62-p14-init01`: PASS, ready 4.020 s, GPU peak 6600 MiB.
- `c62-p14-cold51301`: PASS load/forward, 513 prompt IDs + 4 capped completion tokens, prompt eval 76.791 s, decode 0.876 s; GPU peak 6660 MiB, cgroup peak 12.104 GB, CPU peak 95.125 C (warning), no guard/OOM/swap.
- Layer map was not emitted at server verbosity 3. Source expects CPU0–22/CUDA23–35 plus output CUDA; actual per-layer map remains INCOMPLETE_EVIDENCE. Single run cannot show speedup, fidelity or quality. C61/C48 FAILs unchanged.
- Next: observe placement and qualify P14 same-profile numerics before contemporary P12/P14 paired timing. Raw remains local; no remote write.
