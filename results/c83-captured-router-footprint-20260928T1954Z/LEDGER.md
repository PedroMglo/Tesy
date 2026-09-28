# C83 captured router footprint

- Base `2460cc1ea41e95036cada72fe8e3f4453f537a80`; reused hash-verified C76b wave-ON router captures. No model was launched.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest tools.test_c83_router_footprint`: 5/5, including four invalid mutants. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c83_router_footprint.py`: 250 router states checked.
- Each selected decode checkpoint has 144 layer/expert keys, 1815.38 MiB of payload. Four checkpoints together contain 394 keys, 4967.08 MiB. Decode0 and decode1 share 74 keys; 70 keys in decode1 were absent from decode0.
- The four sparse checkpoints alone require at most 16 distinct experts per layer, below the existing 32 slots. Intervening demand, evictions and exposed wait are unknown. No L2 benefit or physical NVMe saving is claimed.
- Next: bounded continuous demand/residency trace at the mature streaming boundary, then a physical diagnostic only after capacity and numeric admission. C48/C61/C66 and C78 remain FAIL; C82 remains not admitted. No default or remote change.
