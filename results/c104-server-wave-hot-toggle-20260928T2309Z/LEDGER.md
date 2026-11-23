# C104 ledger

- Measurement commit `91d7fd00f300ebd0df61b63d74ce473420cc311d`. Command: `systemd-run --user --scope -p MemoryMax=19327352832 -p MemorySwapMax=0 -- env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c104_server_wave_hot_toggle.py run results/c104-server-wave-hot-toggle-20260928T2309Z --run-id <RUN_ID> --measurement-commit 91d7fd00f300ebd0df61b63d74ce473420cc311d`.
- Order: c104-p1-on, c104-p1-off, c104-p2-off, c104-p2-on. Four arms passed. Same C75 binary/libraries, same outputs and cached-prefix counts; only wave-skip environment changed.
- ON versus OFF paired cold-prefill gains +75.345%/+75.356%; decode cold +0.066%/+1.854%, warm +10.087%/+4.589%. `NO_ACTIVE_SKIP_DECODE_PENALTY_OBSERVED_TWO_PAIRS` is diagnostic. C100 `NO_GO_CONFIRM` remains; no M3/M4/default promotion.
- Raw are local and indexed by SHA in `manifest.json`. Next: model-free build/phase diagnosis or a different decode mechanism; do not rerun C100 merely to seek a favorable result.
