# N3 expert-byte inventory boundary

Date: 2026-09-23
Status: source-implemented; locked real GGUF still NOT_RUN_MODEL_REQUIRED.

## Question

Native router traces contain selected expert IDs. Byte-weighted cache analysis needs the encoded weight footprint of each expert in each routed layer.

Tesy must not approximate that footprint as total model bytes divided by global expert count.

## Pinned parser and tensor geometry

The inventory script imports GGUFReader from the gguf-py directory of Tesy's exact llama.cpp pin.

The pinned reader exposes original GGML dimensions and encoded tensor n_bytes. For fused expert tensors, Tesy requires dimension index 2 to equal the locked expert count before deriving any per-expert footprint.

Recognized routed expert weight roles include gate, up, down and compatible gate_up/ch fused variants.

Every expected routed layer must be present and the role set must remain consistent across layers unless a future architecture-specific amendment is frozen first.

## Encoded bytes versus runtime transfer

The inventory metric is named per_expert_encoded_weight_bytes.

At the pinned llama.cpp source, selective host-weight handling for GGML_OP_MUL_MAT_ID uses the selected IDs, input->ne[2] as expert count and input->nb[2] as runtime expert stride. It can group consecutive experts and include bounded padding.

Therefore encoded GGUF bytes are not silently relabelled as:
- physical NVMe reads;
- page-cache misses;
- DRAM traffic;
- PCIe bus bytes;
- CUDA copy bytes;
- runtime allocation/repacking bytes.

The first simulator uses encoded bytes only for locality/headroom. A performance/traffic claim requires direct observation or a separately validated runtime-copy model.

## Decode conversion

`tesy trace normalize-native` takes native top-k records plus an inventory and emits the existing normalized byte-weighted trace schema.

By default it starts at graph_seq 1 and keeps only one-token graphs. This prevents the initial multi-token prompt graph from being silently called a committed decode token.

Typical sequence after the model is installed:

    python -m pip install -e .deps/llama.cpp/gguf-py
    python scripts/gguf_expert_inventory.py --model-id gpt-oss-20b-mxfp4-gguf --model-path MODEL.gguf --output results/inventory.json
    tesy trace normalize-native results/routing.jsonl --inventory results/inventory.json --output results/decode-bytes.jsonl --min-graph-seq 1
    tesy trace summarize results/decode-bytes.jsonl --windows 1,2,4,8
    tesy simulate --trace results/decode-bytes.jsonl --ram-cache-gib 16 --vram-cache-gib 4

All byte results above remain DERIVED/SIMULATED until physical traffic instrumentation exists.

## Stop conditions

Stop rather than relax the schema if layer count, expert axis, tensor role set, divisibility, expert-ID range or no-replace publication fails.
