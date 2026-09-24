# n-cpu-moe capacity publication physical-host correction

Date: 2026-09-24

Source campaign:
`n-cpu-moe-capacity-20260923T233416Z`

## Review finding

The historical campaign's `doctor.json` recorded
`reference_check.status=PASS`, but the snapshot predates the repository's
virtualization probe and has no `snapshot.virtualization` evidence.

The current reference-host profile has `require_physical_host=true`.
Current validation requires the snapshot to prove
`virtualization.status=PHYSICAL`; missing virtualization evidence is
`unknown`, not physical-host PASS.

The capacity projections used campaign-start free VRAM/RAM values, so the
publication cannot retain a reference-laptop admission decision without
physical-host provenance.

## Preservation boundary

No source-campaign artifact was deleted, rewritten or relabelled.

In particular, the following remain byte-for-byte historical evidence:

- `doctor.json`;
- `admission-context.json`;
- `capacity-summary.json`;
- per-N `llama-fit-params` outputs;
- build/backend/model provenance.

The original capacity summary still records its projected admitted and rejected
sets. Those values are descriptive source output only.

## Publication correction

The publication layer is now:

`INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN`.

No N value is currently admitted or rejected by the publication as a physical
reference-host capacity gate.

`publication-manifest.json` now records:

- `physical_host_status=NOT_PROVEN`;
- empty admitted/rejected publication sets;
- `performance_gate=INCONCLUSIVE`;
- the original projected sets under
  `historical_source_projection=PRESERVED_NOT_ADMITTED`.

`RESULT.md` states the same boundary.

## Future prevention

`scripts/publish_n_cpu_moe_capacity_result.sh` now rejects publication unless:

- `doctor.reference_check.status == PASS`;
- `doctor.snapshot.virtualization.status == PHYSICAL`.

The focused publication test fixture already represents a proven physical host,
and a new negative test rejects the historical missing-virtualization shape.

## Decision

Do not rerun this historical campaign under the same identity.

A new campaign identity with current physical-host verification is required
before any N point can be promoted as an admitted reference-host capacity
decision.

The source-backed memory projections remain usable as descriptive estimator
outputs. No measured VRAM/RAM traffic, timing, Tesy speedup, >RAM or novelty
claim follows.

## Validation status

Source/static correction: **REPRODUZIDO**.

Focused test execution after this correction:
`NOT_RUN_LOCAL_CHECKOUT_REQUIRED`.

The PR head changed and therefore requires a fresh model-free CI run before it
is merge-ready.
