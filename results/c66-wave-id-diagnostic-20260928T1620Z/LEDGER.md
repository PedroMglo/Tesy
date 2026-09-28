# C66 routed-ID diagnostic

- Backend source-only diagnostic `1c6f503bbb2ee0ee315540a17cbfb6b2bab68f22`; Tesy measurement `9f8a7bf23939641b7b5c1d9995e3caf1517dc7ac`. The patch only checks the incoming ID buffer and aborts with location/value; no routing or weight change.
- `python3 tools/c66_wave_id_diagnostic.py run results/c66-wave-id-diagnostic-20260928T1620Z --measurement-commit 9f8a7bf23939641b7b5c1d9995e3caf1517dc7ac`: plain P12 arm passed (69.772 s). Observer OFF capture aborted after 16.571 s at layer 25/wave 0/index 0, ID −1043122089, valid range 0–127. No ON arm, timing or fidelity promotion.
- The 26 partial layer0 payloads match C61 OFF byte-for-byte. The C66 capture was incomplete; process telemetry ended abruptly with SIGABRT and the bounded receipt records `REQUIRED_PROCESS_TELEMETRY_MISSING`. Observed CPU 78 °C/GPU 52 °C/GPU total 5624 MiB until abort, with zero sampled swap; these are not complete-run resource bounds.
- Raw 27796587 B in 41 local files, hashes in `manifest.json`. C48/C61 FAILs remain unchanged. Next: model-free observer callback discriminant; no further C57 physical run until that yields a safer, distinct test.
