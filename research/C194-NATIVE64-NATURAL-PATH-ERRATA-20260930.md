# C194 — natural entrypoint root-path errata

## Result

SOURCE_AUDITED and REPRODUZIDO_MODEL_FREE: C193's first A32 attempt failed **before model Popen**. The 61-observation inventory was valid, but its receipt recorded a relative file path. The mature C2 server derives an absolute inventory root from its absolute output_root and correctly rejected the path-identity discrepancy. This is an integration defect, not a hardware, numerical or native64 performance result.

Measurement HEAD: 3164c8a9c6d5e9d91a5573baf84dc3c02981c003. Original decision/receipt/raw remain immutable. effective-decision.json links their hashes and classifies the arm FAIL_HARNESS_PREMODEL; the three later S arms and C are NOT_RUN.

## Discriminating proof and repair

The original row hash, policy digest, E18 cap and 61 sensor/resource observations revalidate. A temporary in-memory receipt copy with only its path normalized validates at the **recorded prelaunch-check timestamp**, 0.153841 s after the final observation (see exact value in root-cause.json). This does not create a historical launch or PASS and is not a fresh live admission.

Resolve root at `arm()` and `family()` entry **before collection**. The strict inventory path/content/freshness checks remain unchanged. Two new regressions exercise the actual collect→require_inventory→C2 freshness→Popen boundary from a relative invocation; a deliberately relative receipt alias is still rejected. Sensors, clock and filesystem/model identity use explicit fixtures; the gate is not mocked. The existing imported four-arm prelaunch negative test also runs. Three test methods PASS; no weights.

## Continuation authority

The owner permits model-free harness repair but explicitly forbids replacement physical arms in this family. No second S attempt is made, despite remaining budget. N/C191's numeric PASS and W/C192's paired timing GO remain valid. Native64 useful natural latency and confirmation remain NOT_DEMONSTRATED/NOT_RUN; this is not NO_GO_NATIVE64 performance.

## Next discriminant

Under a new explicit authorization for a natural family, freeze a new output identity with this root-path correction and the unchanged S workload/gates. Execute the four natural arms, then confirmation only if S passes and the complete envelope is admitted. N and W need no routine repetition if their numeric/binary/library identities remain valid. No new quota, kernel or backend is justified by this harness failure.
