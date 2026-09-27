# C18 CPU100 thermal retest

- Base: C17 closure `b93a27e`; new branch `campaign/120b-cpu100-thermal-retest-20260927-1745utc`. Source/model/backend/inputs from C17; CPU warning 95 C and stop 100 C are prospective. Official AMD Tjmax 100 C.
- Six old CPU95 stops are preserved in `prior-fails-preserved.json`; original receipts are untouched. C16 and two premeasurement C18 roots launched no model.
- New physical units: only 513+4 cold P8/P12 paired P8→P12; P12→P8 after first pair qualifies. Each starts after >=300 s idle admission.
- Evidence pending. C15 remains source-only/uncompiled/unmeasured; M3/M4 not run.
