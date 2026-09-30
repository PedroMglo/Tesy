# N1 expert-byte inventory boundary

Date: 2026-09-23
Status: DEVELOPMENT_ONLY until exercised against the locked real GGUF

## Purpose

Passive routing traces contain exact selected expert IDs but no byte size. Cache simulation needs a residency-unit size for each (layer, expert).

Tesy derives that size from the exact locked GGUF tensor layout rather than dividing total model bytes by expert count.

## Upstream source boundary

At the pinned llama.cpp commit, MoE expert weights are fused tensors used by GGML_OP_MUL_MAT_ID.

The scheduler selective host-to-accelerator copy path obtains selected IDs from node->src[2], uses the third fused-tensor dimension as expert count, uses runtime input->nb[2] as the expert copy stride, groups consecutive selected expert IDs, and may copy up to 512 extra padding bytes per copied group/tensor.

This is a runtime transfer rule.

## Tesy encoded inventory

scripts/gguf_expert_inventory.py reads the exact GGUF through the gguf-py package from the pinned llama.cpp checkout.

It identifies fused expert tensors such as blk.N.ffn_gate_exps.weight, blk.N.ffn_up_exps.weight and blk.N.ffn_down_exps.weight, plus compatible gate_up/ch variants.

For each layer the inventory records encoded_tensor_n_bytes / n_experts for each fused expert tensor and sums the roles. This quantity is named per_expert_weight_bytes.

## Critical claim boundary

per_expert_weight_bytes is an encoded GGUF layout footprint. It is not automatically equal to physical SSD reads, page-cache misses, DRAM traffic, PCIe bus bytes, CUDA copy bytes, runtime nb[2] after backend repacking, or scheduler padding.

The initial simulator uses encoded bytes only for locality/headroom analysis. A future runtime/performance campaign needs observed transfer counters or a specifically validated runtime-stride model.

## Pipeline

After the locked model exists on the physical host:

1. Verify model SHA/bytes.
2. Bootstrap the exact llama.cpp pin.
3. Install the pinned local gguf-py package into the Tesy virtualenv if required:

    python -m pip install -e .deps/llama.cpp/gguf-py

4. Create the inventory with no-replace output:

    python scripts/gguf_expert_inventory.py --model-id gpt-oss-20b-mxfp4-gguf --model-path ~/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf --output results/gpt-oss-20b-expert-inventory.json

5. Validate a raw route trace.
6. Normalize it:

    tesy trace normalize-raw results/raw-routing.jsonl --inventory results/gpt-oss-20b-expert-inventory.json --output results/routing-normalized.jsonl

7. Inspect locality:

    tesy trace summarize results/routing-normalized.jsonl --windows 1,2,4,8

8. Only then run cache simulations.

## Stop conditions

Stop N1 if expected expert tensors are absent, layer set differs from the locked model, expert dimension differs from metadata, tensor roles differ across layers unexpectedly, encoded bytes are not divisible by fused expert count, or raw IDs fall outside inventory bounds.

Do not change expected geometry after seeing a mismatch. Inspect the architecture and create a prospective format update if needed.
