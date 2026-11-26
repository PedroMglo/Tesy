"""Compile and inspect the Tesy AVX2-ordered Vulkan gate without opening a GPU."""

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
UPSTREAM = run_path(HERE.parent / "radv/compile.py")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(module):
    words = struct.unpack(f"<{len(module) // 4}I", module)
    if words[0] != 0x07230203:
        raise ValueError("SPIR-V magic")
    imports = set()
    fused = 0
    precise = 0
    barriers = 0
    pos = 5
    while pos < len(words):
        size, op = divmod(words[pos], 65536)
        if size == 0 or pos + size > len(words):
            raise ValueError("malformed SPIR-V")
        args = words[pos + 1 : pos + size]
        if op == 11 and module[(pos + 2) * 4 : (pos + size) * 4].rstrip(b"\0") == b"GLSL.std.450":
            imports.add(args[0])
        if op == 12 and args[2] in imports and args[3] == 50:  # GLSL.std.450 Fma
            fused += 1
        if op == 71 and args[1] == 42:  # NoContraction
            precise += 1
        if op == 224:  # OpControlBarrier
            barriers += 1
        pos += size
    if not fused or not precise or barriers != 1:
        raise ValueError("missing FMA, separate rounding or workgroup barrier")
    return {"fma_instructions": fused, "no_contraction": precise, "workgroup_barriers": barriers}


def build(out):
    source = (HERE / "gate.comp").read_bytes()
    compiler = UPSTREAM["SHADER"]
    lib = compiler["abi"]()
    handle = lib.shaderc_compiler_initialize()
    if not handle:
        raise RuntimeError("shaderc init")
    try:
        module = UPSTREAM["compile_one"](lib, handle, "gate.comp", source, {}, 2, True)
    finally:
        lib.shaderc_compiler_release(handle)
    row = inspect(module)
    with (out / "gate.spv").open("xb") as f:
        f.write(module)
    return dict(
        status="PASS_ORDERED_SHADER_BUILD",
        compiler_sha256=compiler["COMPILER_SHA"],
        source_sha256=digest(source),
        module_sha256=digest(module),
        protocol_sha256=digest((HERE / "protocol.md").read_bytes()),
        build_source_sha256=digest(Path(__file__).read_bytes()),
        module_bytes=len(module),
        **row,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    out = parser.parse_args().new_output_dir
    os.umask(0o077)
    out.mkdir()
    try:
        result = build(out)
    except Exception as e:
        result = {"status": "FAIL_PRESERVED", "reason": str(e)}
    with (out / "receipt.json").open("x") as f:
        print(json.dumps(result, indent=2, sort_keys=True), file=f)
    print(result)
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
