# C106 ledger

- Model-free command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c106_l2_trace_screen` (4 passed), then `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c106_l2_trace_screen.py` on hash-checked C105 trace.
- 2500 absent-primary demands. 1/2/3 GiB global LRU inserting every load saved 0/0.04/0.08% fixed-trace logical demand bytes; optimistic eviction-only insert saved 8.84/11.40/13.36%. This is below the 20% investment gate in 189+32.
- No L2 implementation or model run. Warm153 reuse, equal-memory alternative and physical NVMe savings NOT_RUN. A draft decision with an arithmetic wording error is preserved separately; corrected `decision.json` reports only 82,640,896 B E18 preventive margin for a 3 GiB L2 before overhead. Next: bound and, if justified, trace a 512-prefix/153-new-ID session; otherwise pivot to decode overlap/compute.
