#!/usr/bin/env python3
"""Bound the pinned per-layer MoEStream slab using the original Tesy GGUF header."""

import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

PIN = "cfec450c1772a832fba57b41b0c0686416eaf304"
INSPECTOR = "research/tools/analysis/gguf_inspect.py"
INSPECTOR_SHA = "1182b7a664b0469882a90154c83ee32edb88f417c1f93f6f797a835ad80b7308"
HEADER_SHA = "ab931ef553e32c03e325cb2c7b322b2f52dcb231b6cda088797e515467cfec2c"
MODEL_SIZE = 63_387_346_208
HEADER_SIZE = 13_022_240
L, E, K, D = 36, 128, 4, 2880
SOURCES = (
    INSPECTOR,
    ".env.example",
    "Dockerfile",
    "src/apply.py",
    "src/llama-moestream.cpp",
    "src/expert_cache.cpp",
    "src/expert_cache.hpp",
    "src/entrypoint.sh",
    "docs/findings/S40-header-sizing.md",
    "docs/findings/S41-frac-curve.md",
    "docs/findings/S47-every-model-verified.md",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify(upstream, model):
    def git(*cmd):
        return subprocess.check_output(["git", "-C", upstream, *cmd])

    require(git("rev-parse", "HEAD").decode().strip() == PIN, "upstream HEAD differs")
    sources = {}
    for name in SOURCES:
        blob = git("show", PIN + ":" + name)
        require((upstream / name).read_bytes() == blob, "source differs from pin: " + name)
        sources[name] = hashlib.sha256(blob).hexdigest()
    require(sources[INSPECTOR] == INSPECTOR_SHA, "inspector digest")
    before = model.stat()
    require(before.st_size == MODEL_SIZE, "GGUF size")
    with model.open("rb") as stream:
        header = stream.read(HEADER_SIZE)
    require(hashlib.sha256(header).hexdigest() == HEADER_SHA, "GGUF header digest")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("pinned_gguf_inspect", upstream / INSPECTOR)
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    table = inspector.parse(model)
    kv = table["kv"]
    require(
        table["data_start"] == HEADER_SIZE and not kv.get("split.count", 0) > 1,
        "single-file data boundary",
    )
    require(
        [kv["gpt-oss." + k] for k in ("block_count", "expert_count", "expert_used_count")]
        == [L, E, K],
        "router geometry",
    )
    pattern = re.compile(r"blk\.(\d+)\.ffn_(gate|up|down)_exps\.weight")
    found = set()
    other_bytes = 0
    for t in table["tensors"]:
        # Every tensor in this particular header is either F32, Q8_0 or MXFP4.
        block, size = {0: (1, 4), 8: (32, 34), 39: (32, 17)}[t["type"]]
        shape = t["dims"]
        require(shape[0] % block == 0, "invalid block boundary")
        encoded = (math.prod(shape) // block) * size
        require(encoded == t["nbytes"], "unexpected padding or overlapping encoded payloads")
        match = pattern.fullmatch(t["name"])
        if not match:
            other_bytes += encoded
            continue
        require(t["type"] == 39 and shape == [D, D, E], "expert weight format")
        found.add((int(match[1]), match[2]))
        stride = D * D // block * size
        for expert in range(E):
            address = t["abs_offset"] + expert * stride
            require(address >= HEADER_SIZE and address + stride <= MODEL_SIZE, "file range")
            require(address + stride <= t["abs_offset"] + encoded, "expert stride")
    require(
        found == {(i, r) for i in range(L) for r in ("gate", "up", "down")},
        "missing recognized role",
    )
    require(
        other_bytes + 3 * L * D * D // 32 * 17 * E == MODEL_SIZE - HEADER_SIZE,
        "tensor conservation",
    )
    after = model.stat()
    require(
        (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
        == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
        "GGUF changed",
    )
    return {
        "header_sha256": HEADER_SHA,
        "tensor_count": len(table["tensors"]),
        "other_encoded_bytes": other_bytes,
        "expert_ranges_verified": len(found) * E,
        "source_sha256": sources,
    }


def calculate():
    encoded_role = D * D // 32 * 17
    across_layers = 3 * encoded_role * L
    other = MODEL_SIZE - HEADER_SIZE - E * across_layers
    cap = 8 * 2**30 - 512 * 2**20
    rows = []
    for ub in (1, 2, 32):
        # Minimum with explicit low frac; allocation includes one null slot per layer.
        union = E * (1 - (1 - K / E) ** ub)
        slots = max(8, min(E, int(1.15 * union) + K))
        slab = (slots + 1) * across_layers
        rows.append(
            {
                "max_ubatch": ub,
                "usable_slots": slots,
                "slab_bytes": slab,
                "all_gpu_slabs_exceed_cap": slab > cap,
                "headroom_after_all_fixed_on_gpu_bytes": cap - slab - other,
                "worst_case_union": min(E, ub * K),
            }
        )
    return {
        "evidence": "FORMAL",
        "source_commit": PIN,
        "device_budget_bytes": cap,
        "expert_role_bytes": encoded_role,
        "per_slot_all_layers_bytes": across_layers,
        "one_arena_bytes": math.ceil(E * encoded_role * 3 / 4096) * 4096,
        "lazy_host_staging_bytes": encoded_role * 3 * 32,
        "other_encoded_bytes": other,
        "slab_floor": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.model) != bool(args.upstream):
        parser.error("--model and --upstream must be supplied together for header verification")
    result = calculate()
    if args.model:
        result["verified"] = verify(args.upstream, args.model)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
