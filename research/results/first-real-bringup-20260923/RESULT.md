# First real bring-up: campaign ledger

Base: `a1aada5f24fb06d66b08566bf0d127ec3b78f994`. Branch: `research/first-real-bringup-20260923`. Prospective protocol: `research/FIRST-REAL-BRINGUP-PROTOCOL-20260923.md`.

## Campaign 1: `results/bringup-20260923T203354Z`

Status: **INCOMPLETE_INTERRUPTED**, not PASS. The agent turn was interrupted while the native tracer build was at 26%. The runner process ended; there is no stock smoke, trace, graph validation, count-space result or inventory in this campaign. Its output directory is preserved.

### Measured and diagnostic evidence

- `doctor-reference.json`: reference host identity PASS; Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB nominal RAM, internal NVMe model mount, CUDA toolkit 13.3.73 observed.
- `model-preflight.json`: model verification PASS; locked 12,109,564,352-byte GGUF, SHA-256 recorded in protocol.
- `capacity-preflight.json`: static plan produced. This is not a successful load.
- Pinned stock llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691` built with CUDA 13.3.73/GCC 15.3.1 for compute capability 89. `llama-cli --list-devices` showed the NVIDIA RTX 4060 Laptop GPU. Binary SHA-256: `e0bb036da22557d9a0001ac3cbc46840b65e0cd8e766ba8186267be09baca6f4`.
- Native tracer build: interrupted at 26%; result **NOT_RUN**, no native binary yet.
- An auxiliary `nvidia-smi` query failed transiently once during build and succeeded on immediate retry. No kernel NVIDIA/Xid messages appeared in a recent journal query. Cause unknown; do not infer a stable driver fault from this alone.

### Decision and next gate

No code defect is demonstrated by the interruption. Preserve this campaign, record the event in this commit, then use a new no-replace output root. The incremental stock/native build trees may be reused because their pinned source checkout and toolchain cache remain clean and identified. Next gate: complete native tracer build, then stock smoke and trace equality.
