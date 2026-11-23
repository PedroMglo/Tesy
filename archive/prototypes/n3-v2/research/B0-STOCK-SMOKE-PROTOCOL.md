# B0 stock smoke campaign

Date: 2026-09-23
Status: prospective diagnostic protocol
Formal/performance qualification: no

`scripts/run_stock_smoke.sh` is the first model-bearing command after the user installs the locked gpt-oss-20b GGUF and builds the pinned stock llama.cpp.

It performs fail-closed provenance/admission checks before opening the model:
- live host snapshot;
- clean pinned source + binary probe;
- model filename/size/SHA verification where locked;
- capacity admission.

The actual smoke uses the pinned CLI with:
- context 4096;
- 16 generated tokens;
- `--gpu-layers auto`;
- fit enabled with 1024 MiB device margin;
- greedy temperature 0 / top-k 1 / seed 42;
- warmup disabled because this is a bounded bring-up diagnostic.

This is intentionally not a throughput campaign. Automatic fit may select a placement based on current free VRAM. A later benchmark campaign must freeze the observed placement or an explicit alternative before comparison.

Outputs are no-replace and retain stdout, stderr/time, pre/post RAM state and NVIDIA snapshots.

A smoke PASS establishes only that the locked stock combination can load and generate under the observed host state. It does not establish chat quality, Tesy optimization, expert-cache benefit or >RAM behavior.

After B0:
1. pair trace OFF/ON with `scripts/compare_trace_exactness.sh`;
2. inspect raw routing summary/headroom;
3. only then freeze B1 CPU-MoE calibration points.
