# First real bring-up: campaign ledger

Base: `a1aada5f24fb06d66b08566bf0d127ec3b78f994`. Branch: `research/first-real-bringup-20260923`. Prospective protocol: `research/FIRST-REAL-BRINGUP-PROTOCOL-20260923.md`.

## Campaign 1: `results/bringup-20260923T203354Z`

Status: **FAIL_NATIVE_BUILD**, not PASS. An interruption of the agent turn did not stop this runner. It continued into the native tracer build. A second runner was mistakenly started against the same shared native build tree, then terminated as soon as the overlap was noticed. The first runner subsequently failed at CUDA library link: `ld.bfd: cannot find .../fattn-tile-instance-dkq256-dv256.cu.o`. There is no stock smoke, trace, graph validation, count-space result or inventory in this campaign. Its output directory is preserved.

### Measured and diagnostic evidence

- `doctor-reference.json`: reference host identity PASS; Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB nominal RAM, internal NVMe model mount, CUDA toolkit 13.3.73 observed.
- `model-preflight.json`: model verification PASS; locked 12,109,564,352-byte GGUF, SHA-256 recorded in protocol.
- `capacity-preflight.json`: static plan produced. This is not a successful load.
- Pinned stock llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691` built with CUDA 13.3.73/GCC 15.3.1 for compute capability 89. `llama-cli --list-devices` showed the NVIDIA RTX 4060 Laptop GPU. Binary SHA-256: `e0bb036da22557d9a0001ac3cbc46840b65e0cd8e766ba8186267be09baca6f4`.
- Native tracer build: **FAIL** at link. No native binary was produced. The two runners overlapped in the same CMake build tree; this is a demonstrated campaign isolation violation and the likely cause of the missing object. The precise file-removal operation was not captured.
- An auxiliary `nvidia-smi` query failed transiently once during build and succeeded on immediate retry. No kernel NVIDIA/Xid messages appeared in a recent journal query. Cause unknown; do not infer a stable driver fault from this alone.

### Decision and next gate

The old statement that this runner ended on turn interruption was wrong and is superseded here. Add an exclusive runner lock and a cheap contention regression test. Preserve the failed native build tree by renaming it; use a fresh native build tree and a new campaign identity. Next gate: complete native tracer build, then stock smoke and trace equality.

## Campaign 2: `results/bringup-20260923T204412Z`

Status: **ABORTED_CONCURRENT**, not PASS. Started while Campaign 1 was active, violating build isolation; process group 108220 was terminated before model execution. This output is preserved. It reached native CUDA compilation but has no valid build, smoke, trace or inventory result. No model-bearing scientific outcome is inferred from it.
