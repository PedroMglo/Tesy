# C16 ledger

- New branch from `d3beba8`; original backend binary/model unchanged. C15 remains source-only.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 tools/c16_thermal_audit.py results/c16-thermal-recovery-20260927T1632Z/thermal-recovery-audit.json`: 12 limited PASS, four thermal FAIL, C8 historical preload confirmation hashes PASS. Two model-free audit attempts preserved before final parser rule.
- 48 model-free tests PASS; original P8/P12 server argv differ only in `-ngl`; 513 token IDs SHA matches. Full model hash, GPU, sensors, AC/power, port, E18 zero-swap scope and sampler checked. Physical C16 arms: NOT_RUN at freeze.
- Next: commit the measurement tree; then T0 P8 init after fresh 5-minute idle admission. Each following arm needs its own admission and result checkpoint. No automatic retry. Default unchanged.
- T0 P8 idle under `3349c13c0ce18b7132f2c45bcd98be4332d49057`: 494 samples over 394.452 s; one gap at 80.029→81.121 s was 1.092 s, above the frozen 1 s cadence. Temperatures stayed below admission maxima (CPU53/GPU42/NVMe35.85 C). Own scope PID154603 was stopped before server launch; `raw/` has no model file, GPU compute list and port18367 are clear. `THERMAL_PREFLIGHT_BLOCKED` is a telemetry/harness gate, not evidence that cooling failed. New identity and sampler repair required.
