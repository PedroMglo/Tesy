"""Check the pinned RHS source expressions on two synthetic blocks. No native dispatch."""

import argparse
import hashlib
import json
import struct
from fractions import Fraction
from pathlib import Path

PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
VK = "ggml-vulkan/vulkan-shaders/"
SOURCES = {
    "ggml-common.h": "578a0cffc8284387191aceb7128cc39d92a3b3edc199fe0b79ed8627fefcc633",
    "ggml-cpu/ggml-cpu.c": "bda1c2c81077d89813c3b4776079a5ddf65eaf28bf1e33338473818cc56831f5",
    "ggml-cpu/arch/x86/quants.c": (
        "3c489fdc77e3ab484a5f188bff9c60c0e9483c951ed65c1a562a04c249d5628e"
    ),
    "ggml-vulkan/ggml-vulkan.cpp": (
        "63140287d1ed1722d69d30881e4140da9306b3231bc83b07937bc7bbd30dbc77"
    ),
    VK + "quantize_q8_1.comp": "9f16a5781b7c2ffebec4d18debbeb03ba86be6b473b69dd658aa42d1188825cd",
    VK + "types.glsl": "e63375daed0627d0e7d04a21ead2ad17106ee8296cecfbc9d0f6b7fa8e6bf7e9",
    VK + "dequant_funcs.glsl": "be596a0e9a134c3e0c291dd957f666e74bc6b6368dae94f93bcfec66b81b460d",
    VK
    + "mul_mat_vecq_funcs.glsl": "3fd3fb25cfdb3214eeb8659bbeaf0bc0f6d095d9314ca7536933d7cafd52bcf6",
    VK + "mul_mmq_funcs.glsl": "ccac1efc8af5006edffbf43ae120b514fde899fcc89ec863526be23b9e906ef0",
    VK
    + "vulkan-shaders-gen.cpp": "96f8370fc1bfb226147ad45edaa0c874839c5078373f36265028287c3f180d08",
}


def f32(x):
    """Nearest-even positive binary32, with an exact check against the next neighbour."""
    exact = Fraction(x)
    if exact < 0:
        raise ValueError("this witness only has nonnegative values")
    word = struct.pack(">f", float(exact))
    nearest = Fraction(struct.unpack(">f", word)[0])
    if exact != nearest:
        bits = int.from_bytes(word, "big")
        neighbour = bits + (1 if exact > nearest else -1)
        other = Fraction(struct.unpack(">f", neighbour.to_bytes(4, "big"))[0])
        error = abs(exact - nearest)
        if error > abs(other - exact) or (error == abs(other - exact) and bits % 2):
            raise ArithmeticError("binary32 rounding")
    return nearest


def word(x):
    return struct.pack(">f", float(x)).hex()


def inputs(maximum, v):
    """The remaining 30 coordinates and all corresponding weights are zero."""
    d = f32(maximum / 127)
    id_cpu = f32(127 / maximum)
    id_glsl = f32(1 / d)
    scaled_cpu = f32(v * id_cpu)
    scaled_glsl = f32(v * id_glsl)
    if scaled_glsl.denominator == 2:
        raise ArithmeticError("GLSL round at an ambiguous half")
    q_cpu = round(scaled_cpu)  # round-to-nearest-even for the AVX instruction
    q_glsl = round(scaled_glsl)  # nearest is unique here
    half_d = struct.pack(">e", float(d))
    stored = Fraction(struct.unpack(">e", half_d)[0])
    return {
        "max_f32": word(maximum),
        "v_f32": word(v),
        "d_f32": word(d),
        "d_f16": half_d.hex(),
        "cpu_inv_f32": word(id_cpu),
        "glsl_inv_f32": word(id_glsl),
        "cpu_scaled_f32": word(scaled_cpu),
        "glsl_scaled_f32": word(scaled_glsl),
        "cpu_q": q_cpu,
        "glsl_q": q_glsl,
        "cpu_dot_f32": word(f32(q_cpu * stored)),
        "glsl_q8_dot_f32": word(f32(q_glsl * stored)),
        "float_rhs_dot_f32": word(v),
    }


def check(backend):
    for path, expected in SOURCES.items():
        digest = hashlib.sha256((backend / "ggml/src" / path).read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"C269 source digest mismatch: {path}")

    tiny = [inputs(f32(1), f32(v)) for v in (0, Fraction(1, 1024))]
    rounding = [inputs(f32(11), f32(v)) for v in (Fraction(33, 254), Fraction(3, 16))]
    if [r["cpu_q"] for r in tiny] != [0, 0] or [r["float_rhs_dot_f32"] for r in tiny] != [
        "00000000",
        "3a800000",
    ]:
        raise ArithmeticError("float discriminator")
    if (rounding[0]["v_f32"], rounding[0]["cpu_scaled_f32"], rounding[0]["glsl_scaled_f32"]) != (
        "3e050a14",
        "3fc00000",
        "3fbfffff",
    ):
        raise ArithmeticError("quantizer discriminator inputs or intermediates")
    if [r["cpu_q"] for r in rounding] != [2, 2] or [r["glsl_q"] for r in rounding] != [1, 2]:
        raise ArithmeticError("quantizer discriminator codes")

    return {
        "status": "PASS_C269_RHS_SOURCE_EXPRESSION_WITNESSES",
        "reference_commit": PIN,
        "sha256_relative_to_ggml_src": SOURCES,
        "program_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "f32_bits_order": "most significant first",
        "geometry": {
            "block_values": 32,
            "K": 2880,
            "blocks_per_row": 90,
            "q8_0_bytes_per_row": 3060,
        },
        "float_witness": tiny,
        "q8_1_witness": rounding,
        "operator_executions": 0,
        "radv_dispatch": "NOT_RUN",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, type=Path)
    print(json.dumps(check(parser.parse_args().backend), indent=2, sort_keys=True))
