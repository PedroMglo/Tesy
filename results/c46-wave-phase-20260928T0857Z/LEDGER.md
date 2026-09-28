# C46 diagnostic ledger

- Source backend: isolated `/tmp/tesy-c46-backend-20260928`, commit `005e8ff8dd264a2fdecd6dd99e42580d8d2674dc`, based on C15 `1691fb65a00c963ec3aa64a5b66a1b951de52d15`.
- Change: NVTX ranges around server prefill/generation decode and instant wave markers containing layer, wave, active pairs and all issued pair slots. No algorithm, model weights or router changes.
- Model-free: CUDA arch 89 Release server built with GCC 15.3.1/CUDA 13.3; `llama-server --help` and an NVTX range/mark SQLite smoke passed. The smoke raw remains local under `raw/`.
- Frozen single model unit: 513 official IDs + 4 greedy completion, same E18/CPU100 guards and C43 output reference; timing instrumented and diagnostic only. See `protocol.json` and per-run protocol.
- C45 result carried forward: CPU MMID interval union 58.307 s, 73.324% of uninstrumented control prefill, a loose all-phase upper bound. Prior failures unchanged.
- Physical run, phase density, same-profile output and investment decision: NOT_RUN at protocol freeze.

- C46 run passed E18/CPU100 and the four-token C43 output bridge; profiled prefill 79.583 s is diagnostic. CPU max 95.125 °C warning; zero swap/OOM.
- Prefill: 5,565 wave marks, 71,260/708,540 active pair slots (10.057%); MMID union 58.011 s, 55.594 s without tagged I/O overlap (69.911% of C43 control prefill).
- Frozen investment screen passed. Compaction, full-logit reference and production speedup remain NOT_RUN. Next: C47 source/static feasibility and canonical boundary plan.
