"""Build exactly one reachable C269 MXFP4 matvec-ID pathway from pinned git objects."""

import ctypes as C
import hashlib
import re
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RHS = HERE.parents[1] / "rhs_device"
SHADER = run_path(RHS / "compile_shader.py")
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
DIR = "ggml/src/ggml-vulkan/vulkan-shaders/"
INCLUDE = re.compile(rb'^\s*#include\s+"([a-zA-Z0-9_./-]+)"\s*$', re.M)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compile_one(lib, comp, name, source, defines, target_minor, optimized):
    opt = lib.shaderc_compile_options_initialize()
    if not opt:
        raise ValueError("shaderc options")
    try:
        lib.shaderc_compile_options_set_target_env(opt, 0, (1 << 22) | (target_minor << 12))
        lib.shaderc_compile_options_set_optimization_level(opt, 2 if optimized else 0)
        for k, v in defines.items():
            lib.shaderc_compile_options_add_macro_definition(
                opt, k.encode(), len(k), v.encode(), len(v)
            )
        raw = lib.shaderc_compile_into_spv(
            comp, source, len(source), 2, name.encode(), b"main", opt
        )
        if not raw:
            raise ValueError("shaderc result")
        try:
            if lib.shaderc_result_get_compilation_status(raw):
                raise ValueError(lib.shaderc_result_get_error_message(raw).decode())
            return C.string_at(
                lib.shaderc_result_get_bytes(raw), lib.shaderc_result_get_length(raw)
            )
        finally:
            lib.shaderc_result_release(raw)
    finally:
        lib.shaderc_compile_options_release(opt)


def build(backend, out):
    files = {}

    def expand(path):
        src = subprocess.check_output(["git", "-C", str(backend), "show", PIN + ":" + DIR + path])
        files[path] = digest(src)
        return INCLUDE.sub(lambda m: expand(m[1].decode()), src)

    lib = SHADER["abi"]()
    comp = lib.shaderc_compiler_initialize()
    if not comp:
        raise ValueError("shaderc compiler")
    try:
        probe = "feature-tests/integer_dot.comp"
        diagnostic = ""
        try:
            compile_one(lib, comp, probe, expand(probe), {}, 3, False)
            packed = True
        except ValueError as e:
            diagnostic = str(e)
            if not re.search(
                r"extension not supported: ['\"]?GL_EXT_integer_dot_product", diagnostic
            ):
                raise
            packed = False
        defines = dict(
            FLOAT_TYPE="float",
            FLOAT_TYPEV2="vec2",
            DATA_A_MXFP4="1",
            MUL_MAT_ID="1",
            D_TYPE="float",
            USE_SUBGROUP_ADD_NO_SHMEM="1",
        )
        if packed:
            defines["ACC_TYPE"] = "float"
        else:
            defines.update(B_TYPE="float", B_TYPEV2="vec2", B_TYPEV4="vec4")
        name = "mul_mat_vecq.comp" if packed else "mul_mat_vec.comp"
        source = expand(name)
        module = compile_one(lib, comp, name, source, defines, 2, True)
        (out / "projection.spv").write_bytes(module)
        words = struct.unpack(f"<{len(module) // 4}I", module)
        if words[0] != 0x07230203:
            raise ValueError("not SPIR-V")
        i, capabilities, opcodes = 5, set(), set()
        while i < len(words):
            n, op = divmod(words[i], 65536)
            if n == 0 or i + n > len(words):
                raise ValueError("SPIR-V instruction")
            if op == 17:
                capabilities.add(words[i + 1])
            opcodes.add(op)
            i += n
        if (
            63 not in capabilities or (4450 in opcodes) != packed
        ):  # GroupNonUniformArithmetic, OpSDot
            raise ValueError("subgroup and integer-dot pipeline")
        return dict(
            backend=PIN,
            toolchain=SHADER["COMPILER_SHA"],
            mode="mmvq" if packed else "float",
            defines=defines,
            published_source=files,
            source_expanded_sha256=digest(source),
            module_sha256=digest(module),
            module_bytes=len(module),
            capabilities=sorted(capabilities),
            integer_dot_probe_diagnostic=diagnostic,
            rows_per_group=2 if packed else 4,
        )
    finally:
        lib.shaderc_compiler_release(comp)
