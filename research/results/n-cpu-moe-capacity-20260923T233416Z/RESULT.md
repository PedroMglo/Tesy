# n-cpu-moe capacity-only diagnostic

Campaign: `n-cpu-moe-capacity-20260923T233416Z`

Publication classification:
`INCONCLUSIVE_PHYSICAL_HOST_NOT_PROVEN`.

Build provenance: `PASS`.

The source campaign's `doctor.json` recorded a historical
`reference_check.status=PASS`, but that snapshot predates virtualization
telemetry and contains no `snapshot.virtualization` object. Under the current
reference-host contract, which requires an explicitly proven physical host,
that historical PASS is insufficient for hardware-bearing capacity admission.

The raw campaign and all estimator outputs remain preserved byte-for-byte.
In particular, `capacity-summary.json` still contains the original projected
classification:

- historically projected admitted N values: 12, 16, 20, 24;
- historically projected rejected N values: 0, 4, 8.

Those labels are retained only as source-campaign output. **No N value is
currently admitted or rejected by this publication as a physical reference-host
capacity gate.**

Performance/capacity admission gate: `INCONCLUSIVE`.

The frozen stock auto-fit argv and source-backed `llama-fit-params` memory
projections remain useful descriptive evidence. They are not measured peak
VRAM/RAM, physical transfer traffic, or proof that the campaign executed on the
required physical laptop.

A new campaign identity with current physical-host verification is required
before promoting any projected point as an admitted reference-host capacity
decision.

This campaign stopped before timed llama-server observations. No rejected point
was deliberately loaded to induce OOM.

No Tesy speedup, >RAM execution, physical PCIe/NVMe traffic or novelty claim
follows.
