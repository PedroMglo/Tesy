#!/usr/bin/env python3
"""Compute P8/P12 nominal placement from native GGUF tensor metadata."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from c2_gate import GateError, strict_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def account(path):
    rows = [strict_json(line) for line in path.read_text().splitlines()]
    header, tensors = rows[0], rows[1:]
    if header.get("tensor_count") != len(tensors) or len(tensors) != 687:
        raise GateError("GGUF inventory incomplete")
    by_layer = defaultdict(list)
    unlayered = {}
    for row in tensors:
        name = row["name"]
        if name.startswith("blk."):
            _, layer, suffix = name.split(".",2)
            by_layer[int(layer)].append((suffix,row))
        else:
            unlayered[name] = row
    if set(by_layer) != set(range(36)) or set(unlayered) != \
            {"token_embd.weight","output.weight","output_norm.weight"}:
        raise GateError("unexpected layer/unlayered tensor set")
    layer_sizes = []
    categories = defaultdict(int)
    for layer in range(36):
        expert = 0
        dense = 0
        for suffix,row in by_layer[layer]:
            size = row["n_bytes"]
            if suffix in ("ffn_gate_exps.weight","ffn_up_exps.weight","ffn_down_exps.weight"):
                if row["shape"][-1] != 128 or size != 564019200:
                    raise GateError("expert matrix layout changed")
                expert += size
                categories["expert_encoded_gguf_bytes"] += size
            else:
                dense += size
                categories["biases_gguf_bytes" if suffix.endswith(".bias") else
                           "dense_router_norm_gguf_bytes"] += size
        if expert != 1692057600 or dense != 34155008:
            raise GateError("layer tensor accounting changed")
        layer_sizes.append({"layer":layer,"expert_full_bytes":expert,
                            "nonstream_gguf_bytes":dense})
    per_expert = layer_sizes[0]["expert_full_bytes"]//128
    slot_pool = per_expert*32
    profiles = {}
    for name,first_gpu in (("P8",29),("P12",25)):
        cpu=list(range(first_gpu));gpu=list(range(first_gpu,36))
        profiles[name] = {"ngl":8 if name=="P8" else 12,
            "expected_cpu_layers":cpu,"expected_gpu_layers":gpu,
            "cpu_expert_pools_bytes":len(cpu)*slot_pool,
            "gpu_expert_pools_bytes":len(gpu)*slot_pool,
            "cpu_nonstream_layer_gguf_bytes":len(cpu)*34155008,
            "gpu_nonstream_layer_gguf_bytes":len(gpu)*34155008,
            "output_gpu_gguf_bytes":unlayered["output.weight"]["n_bytes"]+
                                      unlayered["output_norm.weight"]["n_bytes"],
            "token_embedding_cpu_gguf_bytes":unlayered["token_embd.weight"]["n_bytes"]}
    return {"schema":"c7-tensor-accounting-v1","evidence_class":"GGUF metadata and source placement estimate",
        "inventory_sha256":digest(path),"tensor_count":len(tensors),
        "model_data_offset":header["data_offset"],
        "categories_gguf_bytes":dict(categories),"per_expert_streamed_bytes":per_expert,
        "slots_per_layer":32,"slot_pool_per_layer_bytes":slot_pool,
        "profiles":profiles,
        "p12_minus_p8":{"cpu_expert_pools_bytes":-4*slot_pool,
                          "gpu_expert_pools_bytes":4*slot_pool,
                          "gpu_nonstream_layer_gguf_bytes":4*34155008},
        "unbounded_or_runtime_only":["KV and recurrent KV allocation","staging and pinned host memory",
          "graph/workspace and CUDA allocator reserves","page cache and metadata", "actual output placement"],
        "admission_policy":{"gpu_total_mib_at_most":6500,"cgroup_gib_at_most":16.5,
                            "rss_gib_at_most":16,"requires_bounded_init":True}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("inventory",type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    with a.output.open("x") as out:
        json.dump(account(a.inventory),out,indent=2,allow_nan=False);out.write("\n")


if __name__=="__main__":main()
