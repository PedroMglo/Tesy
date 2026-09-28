# C55b model-free reproduction

Use a new no-replace root for each rerun; do not overwrite C55b.

```bash
mkdir results/<NEW_C55_ROOT>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c55_inventory.py results/<NEW_C55_ROOT>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -c 'from c24_preflight import scope_test; print(scope_test(19327352832))'
systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c55_monitor_smoke.py results/<NEW_C55_ROOT>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest discover -s tools -p 'test_*.py'
```

The abbreviated scope commands in `protocol.json` describe the original checks; the concrete commands above are the reproduction form. C55b's fixed hashes and result are not replaced by a new run.
