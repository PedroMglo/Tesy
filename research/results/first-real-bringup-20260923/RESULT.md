# First real bring-up: campaign ledger

Base: `a1aada5f24fb06d66b08566bf0d127ec3b78f994`. Branch: `research/first-real-bringup-20260923`. Prospective protocol: `research/FIRST-REAL-BRINGUP-PROTOCOL-20260923.md`.

## Campaign 1: `results/bringup-20260923T203354Z`

Status: **FAIL_NATIVE_BUILD**, not PASS. Campaign HEAD `d21c16bbdf6bdfa8c486e09cfa0590637656b514`. An interruption of the agent turn did not stop this runner. It continued into the native tracer build. A second runner was mistakenly started against the same shared native build tree, then terminated as soon as the overlap was noticed. The first runner subsequently failed at CUDA library link: `ld.bfd: cannot find .../fattn-tile-instance-dkq256-dv256.cu.o`. There is no stock smoke, trace, graph validation, count-space result or inventory in this campaign. Its output directory is preserved.

### Measured and diagnostic evidence

- `doctor-reference.json`: reference host identity PASS; Ryzen AI 9 HX 370, RTX 4060 Laptop 8 GiB, 32 GiB nominal RAM, internal NVMe model mount, CUDA toolkit 13.3.73 observed.
- `model-preflight.json`: model verification PASS; locked 12,109,564,352-byte GGUF, SHA-256 recorded in protocol.
- `capacity-preflight.json`: static plan produced. This is not a successful load.
- Pinned stock llama.cpp `4e416ee7308dd6b581796f1a6241276cd5982691` built with CUDA 13.3.73/GCC 15.3.1 for compute capability 89. `llama-cli --list-devices` showed the NVIDIA RTX 4060 Laptop GPU. Binary SHA-256: `e0bb036da22557d9a0001ac3cbc46840b65e0cd8e766ba8186267be09baca6f4`.
- Native tracer build: **FAIL** at link. No native binary was produced. The two runners overlapped in the same CMake build tree; this is a demonstrated campaign isolation violation and the likely cause of the missing object. The precise file-removal operation was not captured.
- Auxiliary `nvidia-smi` queries failed intermittently during build and succeeded on retry. No kernel NVIDIA/Xid messages appeared in a recent journal query. Cause unknown; do not infer a stable driver fault from this alone.

### Decision and next gate

The old statement that this runner ended on turn interruption was wrong and is superseded here. Add an exclusive runner lock and a cheap contention regression test. Preserve the failed native build tree by renaming it; use a fresh native build tree and a new campaign identity. Next gate: complete native tracer build, then stock smoke and trace equality.

## Campaign 2: `results/bringup-20260923T204412Z`

Status: **ABORTED_CONCURRENT**, not PASS. Campaign HEAD `26504ea1843d88a7f362ee6ce16aadc0fedff721`. Started while Campaign 1 was active, violating build isolation; process group 108220 was terminated before model execution. This output is preserved. It reached native CUDA compilation but has no valid build, smoke, trace or inventory result. No model-bearing scientific outcome is inferred from it.

## Campaign 3: `results/bringup-20260923T205424Z`

Status: **PASS_DIAGNOSTIC_REFERENCE_BRINGUP_PIPELINE**; runner exit code 0. Campaign HEAD `08296f10c74c7edce6c12a265e52c6e504427c9c`, clean at launch. The fresh native build prevented reuse of objects from the overlapping attempts. See `manifest.json` for paths, sizes and SHA-256 of all raw local artefacts. Raw logs, trace, model and binaries remain outside Git.

| Gate | Result | Evidence class and scope |
| --- | --- | --- |
| Reference doctor / model SHA / static capacity | PASS / PASS / ADMISSIBLE_FOR_TEST | MEASURED host and model identity; ESTIMATED capacity admission |
| Pinned stock llama.cpp CUDA build | PASS | MEASURED local build; CUDA 13.3.73, GCC 15.3.1, compute 89, CUDA device listed |
| Pinned native tracer CUDA build | PASS | MEASURED local build against the same source pin |
| Stock llama.cpp smoke | PASS | MEASURED 16-token model load/generation diagnostic; no chat or performance qualification |
| Tracer OFF / ON | PASS / PASS | MEASURED 16 generated IDs in each run |
| OFF vs ON generated token IDs | PASS | Exact equality of those ID lists only; not bitwise or numerical model parity |
| Native graph consistency | PASS | 15 one-token graphs, 24 MoE layers × top-4 signature, zero mismatches |
| Count-space LRU / Belady | PASS_DERIVATION | TRACE_DERIVED; Belady is non-causal offline oracle |
| GGUF expert inventory | INCONCLUSIVE_DEPENDENCY_LOCK_REQUIRED | Diagnostic output retained, but transitive Python dependencies were not frozen prospectively |
| Byte-weighted two-tier LRU | NOT_ADMITTED_DEPENDENCY_LOCK_REQUIRED | Derived from the non-confirmatory inventory; numbers retained only as exploratory diagnostics |
| CUDA performance, physical expert bytes, chat, >RAM, speculation | NOT_RUN | Outside this diagnostic campaign |

### Identities and observed host

Model: `ggml-org/gpt-oss-20b-GGUF` revision `a7443ebb00ba299cbbbf7e9b69487670447ae8c0`, 12,109,564,352 bytes, SHA-256 `52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4`. Embedded tokenizer model `gpt2`; embedded chat-template SHA-256 `3e39477db816e5fb12d05aa593fbd8967969e7fd146f519ec321003939ae723c`. The paired trace uses `--raw-prompt`, so that template is not exercised there.

Backend: llama.cpp source `4e416ee7308dd6b581796f1a6241276cd5982691`, `llama-cli` SHA-256 `e0bb036da22557d9a0001ac3cbc46840b65e0cd8e766ba8186267be09baca6f4`, tracer SHA-256 `72be371eea27d857e28a10940a48f7b4e4141fb6ed9e307a28c5e5cbe3f59263`. Both CMake caches show `GGML_CUDA=ON`, Release, architecture 89, `/usr/local/cuda/bin/nvcc`, GCC/G++ 15.3.1. `llama-cli --list-devices` listed CUDA0 RTX 4060 Laptop GPU. The initial `nvcc: NOT_AVAILABLE` was a PATH finding, followed by the diagnosed GCC 16 incompatibility; no system package or NVIDIA stack change was needed.

Reference doctor: PASS on AMD Ryzen AI 9 HX 370, 24 logical CPUs, RTX 4060 Laptop GPU, driver 615.71.09, 8,585,740,288 GPU bytes total and 8,248,098,816 free at snapshot, 32,698,654,720 RAM bytes total and 25,249,914,880 available, 16,348,868,608 swap bytes total and 16,348,745,728 free. No competing GPU compute process was visible. Model path was on `/dev/nvme0n1p3[/home]` Btrfs. Doctor reported CUDA toolkit OK and GPU temperature 50°C. These are point-in-time observations, not sustained telemetry.

### Quantitative diagnostic results

The stock smoke returned 0 after 16 requested tokens. `/usr/bin/time -v` recorded 8.92 s wall time, 12,353,100 KiB maximum RSS, 16 major page faults and zero swaps. `nvidia-smi` before/after reported 23 MiB used; no in-run VRAM peak was captured. TTFT, sustained TPOT and thermal trajectory were **NOT_RUN**. The single tracer OFF/ON timing logs are retained but are not an overhead comparison or performance claim.

The paired tracer generated the same 16 IDs OFF and ON (token-file SHA-256 `88a5977ac17a17be73f4ed5ff842e473aab28b5c21e557b738d7322420d47627`). The raw routing trace has 384 records across 16 graphs: one 14-token prefill graph and 15 one-token decode graphs. The one-token graphs contain 1,440 expert accesses and 429 distinct layer/expert keys. `--ngl 0` offloaded **0/25 weight layers**; the backend nevertheless reserved a 2.20 MiB CUDA compute buffer. This gate checks zero-layer-offload instrumentation and token equality; it must not be described as strict CPU-only execution or a CPU/GPU benchmark.

| Equal-sized cache slots | LRU loads / hits | Offline Belady loads / hits |
| ---: | ---: | ---: |
| 0 | 1440 / 0 | 1440 / 0 |
| 16 | 1440 / 0 | 1240 / 200 |
| 32 | 1440 / 0 | 1059 / 381 |
| 64 | 1440 / 0 | 781 / 659 |
| 128 | 838 / 602 | 549 / 891 |
| 256 | 526 / 914 | 429 / 1011 |

The diagnostic GGUF inventory produced 24 layers × 32 experts = 768 encoded expert objects, each 13,253,760 bytes, with 10,178,887,680 bytes in merged expert tensors and no rejected tensors. Because `gguf-py` transitive dependencies were not frozen prospectively, this output is retained as exploratory evidence only and is **not an admitted PASS_DERIVATION**. Individual physical expert fetch granularity is also unknown.

Exploratory only: with the prospectively chosen 16 GiB RAM and 4 GiB VRAM byte-LRU capacities and `min_graph_seq=1`, the trace-derived simulation reported 5,685,863,040 encoded expert bytes NVMe→RAM and 6,441,327,360 RAM→VRAM, or 379,057,536 and 429,421,824 bytes respectively per **15 decode-step proxy**. RAM had 429 misses, 57 hits, zero evictions; VRAM had 486 misses, 954 hits, 162 evictions. These values are **NOT_ADMITTED_DEPENDENCY_LOCK_REQUIRED** because their expert-byte inventory dependency was not prospectively locked. Even after a rerun they would remain modeled payload movements, not measured storage reads, page-cache traffic, DRAM traffic, PCIe traffic, latency, or bytes per verified committed token.

### Failures, limits and decision

Campaign 1 failed after an accidental concurrent build; Campaign 2 was aborted. Both remain FAIL/ABORTED and are not reclassified by Campaign 3's PASS. The exclusive `flock` and its contention regression prevent another pair of reference runners from sharing the build tree. An auxiliary `nvidia-smi` call failed transiently during the first build and succeeded on retry; cause remains unknown. The model-bearing Campaign 3 doctor and CUDA device probe passed.

The broad prior-art decision remains `BROAD_NOVELTY_NO_GO / ENGINEERING_AND_MEASUREMENT_GO`. gpt-oss expert `--lazy-mode` remains `STATIC_NO_GO_B2_GPTOSS_EXPERT_LAZY`; vLLM remains B4 comparator. The short trace and simulated bytes provide no Tesy speedup, expert-cache benefit, >RAM support or novelty result. The next discriminating gate is a prospectively frozen stock B0/B1 workload with actual placement, TTFT/TPOT, RAM/VRAM/swap and storage/PCIe telemetry, then comparison to the trace-derived cache hypotheses. Do not implement a native expert cache from this diagnostic result alone.

`gguf-py` came from the pinned llama.cpp source, but its transitive pip dependencies were resolved during this diagnostic campaign rather than pinned prospectively. Their observed versions are in `backend-toolchain.json`; a confirmatory inventory or performance campaign must freeze the full environment beforehand. The first campaign's transient `nvidia-smi` failures also warrant a stability check before any sustained timing claim.
