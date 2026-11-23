# C32 full SWA source check

- Frozen source/raw comparison after C31. No model process authorized in this unit. The decision asks whether a new `--swa-full` profile differs from the one already measured.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c32_swa_source.py` exited 1: `GateError: C29 loaded-state SWA evidence incomplete`. C29 verbosity 3 logs the full-size SWA warning but omits the INFO-level 8192-cell/checkpoint lines. No model run and no audit result were produced. Preserve this gate assumption failure; C32b uses the evidence each log level actually contains.
