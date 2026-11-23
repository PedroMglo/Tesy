# C32b SWA source check

- New model-free identity after C32's frozen checker demanded INFO lines from C29's verbosity-3 log. C32 FAIL is preserved. C29 warning plus command, C31 detailed log, and pinned source are the evidence boundaries.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c32b_swa_source.py` exited 1 before any audit output: `KeyError: 'C31_decision_sha256'`. The frozen C32b protocol omitted an input hash required by the reused input map. No model run. New C32c identity carries the full key set; this failure stays visible.
