# C18 CPU100 thermal retest

- Base: C17 closure `b93a27e`; new branch `campaign/120b-cpu100-thermal-retest-20260927-1745utc`. Source/model/backend/inputs from C17; CPU warning 95 C and stop 100 C are prospective. Official AMD Tjmax 100 C.
- Six old CPU95 stops are preserved in `prior-fails-preserved.json`; original receipts are untouched. C16 and two premeasurement C18 roots launched no model.
- New physical units: only 513+4 cold P8/P12 paired P8→P12; P12→P8 after first pair qualifies. Each starts after >=300 s idle admission.
- Evidence pending. C15 remains source-only/uncompiled/unmeasured; M3/M4 not run.
- `c18-p1-p8-cold513` PASS at measurement `01e64cc5ac1498574258790abd4afec029124e95`: request 90.022 s, prefill 89.113 s, decode 0.905 s; CPU max 95.125 C with 17 warning samples, ACPI cooling 0, zero swap/OOM. Raw SHA `9c58a6ba47711e8225542ae4ebad1f67d587b6b59c575465ddf59b522b0bd8cb`. GPU/port free after exit.
