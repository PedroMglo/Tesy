"""Compile the two authenticated C269 activation shaders offline using shaderc's C ABI."""

import argparse
import ctypes as C
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHADERC = Path("/lib64/libshaderc_shared.so.1")
COMPILER_SHA = "a5f5761e4200c4a35bdf853167522cc3a615106cb3efb76b951f457a91ca3d7b"
REFERENCE_SHA = "56ed61a33abcf79b3673beffbc62f6bc2a4fcdb44145909a8a9369da85750a6e"
PREFIX = "ggml-vulkan/vulkan-shaders/"
SOURCE = "quantize_q8_1.comp"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(value, why):
    if not value:
        raise ValueError(why)


def abi():
    check(sha(SHADERC.read_bytes()) == COMPILER_SHA, "shaderc identity")
    lib = C.CDLL(str(SHADERC.resolve(strict=True)))
    ptr, text, size, enum = C.c_void_p, C.c_char_p, C.c_size_t, C.c_int
    signatures = {
        "compiler_initialize": (ptr, []),
        "compiler_release": (None, [ptr]),
        "compile_options_initialize": (ptr, []),
        "compile_options_release": (None, [ptr]),
        "compile_options_add_macro_definition": (None, [ptr, text, size, text, size]),
        "compile_options_set_optimization_level": (None, [ptr, enum]),
        "compile_options_set_target_env": (None, [ptr, enum, C.c_uint32]),
        "compile_into_spv": (ptr, [ptr, text, size, enum, text, text, ptr]),
        "result_get_compilation_status": (enum, [ptr]),
        "result_get_error_message": (text, [ptr]),
        "result_get_length": (size, [ptr]),
        "result_get_bytes": (ptr, [ptr]),
        "result_release": (None, [ptr]),
    }
    for name, (result, args) in signatures.items():
        func = getattr(lib, "shaderc_" + name)
        func.restype, func.argtypes = result, args
    return lib


def compile_spv(lib, compiler, source, defines):
    options = lib.shaderc_compile_options_initialize()
    check(options, "shaderc options")
    try:
        lib.shaderc_compile_options_set_target_env(options, 0, (1 << 22) | (2 << 12))  # Vulkan 1.2
        lib.shaderc_compile_options_set_optimization_level(options, 2)  # performance
        for key in defines:
            data = key.encode("ascii")
            lib.shaderc_compile_options_add_macro_definition(options, data, len(data), b"1", 1)
        result = lib.shaderc_compile_into_spv(
            compiler,
            source,
            len(source),
            2,
            SOURCE.encode(),
            b"main",
            options,  # compute shader
        )
        check(result, "shaderc missing compilation result")
        try:
            if lib.shaderc_result_get_compilation_status(result):
                raise ValueError(
                    lib.shaderc_result_get_error_message(result).decode(errors="replace")
                )
            return C.string_at(
                lib.shaderc_result_get_bytes(result), lib.shaderc_result_get_length(result)
            )
        finally:
            lib.shaderc_result_release(result)
    finally:
        lib.shaderc_compile_options_release(options)


def inspect(blob, subgroup):
    check(len(blob) >= 20 and len(blob) % 4 == 0, "SPIR-V size")
    words = struct.unpack(f"<{len(blob) // 4}I", blob)
    check(words[0] == 0x07230203 and words[4] == 0, "SPIR-V header")
    pos, entries, capabilities = 5, [], set()
    while pos < len(words):
        length, opcode = divmod(words[pos], 65536)
        check(length > 0 and pos + length <= len(words), "SPIR-V instruction size")
        if opcode == 15:  # OpEntryPoint
            name = blob[(pos + 3) * 4 : (pos + length) * 4].split(b"\x00", 1)[0]
            entries.append((words[pos + 1], name))
        if opcode == 17:  # OpCapability
            check(length == 2, "SPIR-V capability")
            capabilities.add(words[pos + 1])
        pos += length
    check(entries == [(5, b"main")], "one compute entrypoint")
    check((67 in capabilities) == subgroup, "GroupNonUniformClustered branch")
    return f"{(words[1] >> 16) & 255}.{(words[1] >> 8) & 255}"


def compile_modules(backend: Path, out: Path) -> dict:
    backend, out = Path(backend), Path(out)
    ref = (HERE.parent / "rhs/receipt.json").read_bytes()
    check(sha(ref) == REFERENCE_SHA, "RHS source authority")
    reference = json.loads(ref)
    commit = subprocess.check_output(
        ["git", "-C", str(backend), "rev-parse", "HEAD"], text=True
    ).strip()
    check(commit == reference["reference_commit"], "C269 pin")
    check(out.is_dir() and not out.is_symlink(), "build output directory")
    for name in ("shared.spv", "subgroup.spv"):
        check(
            not (out / name).exists() and not (out / name).is_symlink(),
            "SPIR-V output already exists",
        )
    paths = reference["sha256_relative_to_ggml_src"]
    sources = {}
    for name in (SOURCE, "types.glsl"):
        buf = (backend / "ggml/src" / PREFIX / name).read_bytes()
        check(sha(buf) == paths[PREFIX + name], name)
        sources[name] = buf
    include = b'#include "types.glsl"'
    check(
        sources[SOURCE].count(b"#include") == sources[SOURCE].count(include) == 1
        and b"#include" not in sources["types.glsl"],
        "single authenticated include",
    )
    source = sources[SOURCE].replace(include, sources["types.glsl"])
    lib = abi()
    compiler = lib.shaderc_compiler_initialize()
    check(compiler, "shaderc initialization")
    modules = {}
    try:
        for label, defines in (
            ("shared", ["QBLOCK_X4"]),
            ("subgroup", ["QBLOCK_X4", "USE_SUBGROUPS"]),
        ):
            blob = compile_spv(lib, compiler, source, defines)
            version = inspect(blob, label == "subgroup")
            file = label + ".spv"
            with (out / file).open("xb") as dest:
                dest.write(blob)
            check((out / file).read_bytes() == blob, "SPIR-V readback")
            modules[label] = dict(
                file=file,
                sha256=sha(blob),
                size_bytes=len(blob),
                defines=defines,
                spirv_version=version,
            )
    finally:
        lib.shaderc_compiler_release(compiler)
    check(modules["shared"]["sha256"] != modules["subgroup"]["sha256"], "branch identity")
    return dict(
        backend_commit=commit,
        shaderc_sha256=COMPILER_SHA,
        rhs_receipt_sha256=REFERENCE_SHA,
        source_sha256={k: sha(v) for k, v in sources.items()},
        expanded_source_sha256=sha(source),
        target="Vulkan 1.2",
        optimization="performance",
        stage="compute",
        entry_point="main",
        modules=modules,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compile_modules(args.backend, args.output), indent=2, sort_keys=True))
