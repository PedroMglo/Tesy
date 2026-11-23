# C108 ledger

- Commands: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c84_trace_validate tools.test_c106_l2_trace_screen tools.test_c107_history_prefetch_screen`; 16 PASS. Relevant model-free suite: 39 PASS. `python3 tools/c84_trace_validate.py <C105 trace>`: PASS.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c108_trace_errata.py results/c108-trace-errata-20260929T0805Z` produced no-replace compact analysis, ledger and budget snapshot. C105 raw SHA matches original manifest.
- Findings: corrected state labels, final-prefill phase and device lookup; global C106 savings and C107 observed coverage unchanged. Original C100/C102/C103 and older FAILs untouched.
- This unit loaded no model. No physical inference is admitted by the model-free result alone. Next: freeze and preflight the C35/C75 OFF/ON decode discriminator within the existing epoch balance.
