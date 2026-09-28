# C45 NVTX-only profiler

- New identity after C44 CUDA-trace environment mismatch before model. Trace only NVTX CPU intervals; C43 original/C15 plain receipts are immutable references. The C44 FAIL remains preserved.

- C45 profiled run: PASS under E18; greedy four-token output matches C43 original/plain. CPU max 95.125 C warning; no guard/OOM/swap.
- 12,300 tagged CPU MMID intervals: union 58.307 s, 73.324% of uninstrumented original control prefill 79.520 s. This is a loose upper bound across all phases, not removable or exclusive work.
- Next: phase alignment and per-wave active-pair occupancy; C15 compaction and M4 NOT_RUN.
