# N3 expert-byte inventory boundary

Date: 2026-09-23
Status: source-implemented; real locked GGUF not yet inspected in this GitHub session.

## Purpose

Router traces provide selected expert IDs. Byte-weighted cache analysis additionally needs the encoded footprint of one expert in each routed layer.

Tesy does not estimate this as `model_size / expert_count`.

## Pinned GGUF parser

`scripts/gguf_expert_inventory.py` imports `GGUFReader` from the `gguf-py` directory of the exact llama.cpp checkout pinned by Tesy.

The pinned reader exposes tensor name, original GGML dimension list and encoded `n_bytes`.

## Geometry check

For each fused expert tensor such as `blk.N.ffn_gate_exps.weight`, `ffn_up_exps`, and `ffn_down_exps`:

- dimension 2 must equal the locked number of experts;
- encoded tensor bytes must be positive and divisible by expert count;
- every expected routed layer must be present;
- expert tensor role sets must agree across layers unless a future architecture-specific amendment says otherwise.

The inventory then records encoded bytes per expert per tensor role and sums those roles per layer.

## Runtime-copy distinction

At the pinned llama.cpp source, the scheduler's host-weight selective copy path for `GGML_OP_MUL_MAT_ID` uses:

- selected IDs from `node->src[2]`;
- `input->ne[2]` as expert count;
- `input->nb[2]` as runtime expert stride;
- grouping of consecutive selected experts;
- up to 512 bytes of additional padding per copied group/tensor when applicable.

Therefore `per_expert_encoded_weight_bytes` is deliberately **not** called physical transfer bytes.

It is suitable for first locality/headroom simulation. A performance or bus-traffic claim requires runtime stride/transfer validation or direct instrumentation.

## Decode normalization

`tesy trace normalize-native` converts only one-token native graphs at or after a frozen `--min-graph-seq` into the normalized byte-weighted trace consumed by the existing simulator.

Multi-token prompt graphs are not silently relabelled as committed decode tokens.

Example after real-model tracing:

    python -m pip install -e .deps/llama.cpp/gguf-py
    python scripts/gguf_expert_inventory.py --model-id gpt-oss-20b-mxfp4-gguf --model-path MODEL.gguf --output results/inventory.json
    tesy trace normalize-native results/routing.jsonl --inventory results/inventory.json --output results/decode-bytes.jsonl --min-graph-seq 1
    tesy trace summarize results/decode-bytes.jsonl --windows 1,2,4,8
    tesy simulate --trace results/decode-bytes.jsonl --ram-cache-gib 16 --vram-cache-gib 4

All outputs remain diagnostic/simulated until physical traffic instrumentation exists.
