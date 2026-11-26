"""Wire image, finite F32 comparison and consumer-observable equivalence."""

import math
import struct

K = 2880
N = 720
SENTINEL = b"\xa5" * 4


def need(ok, why):
    if not ok:
        raise ValueError(why)


def finite(data, n):
    need(len(data) == n * 4, "F32 extent")
    values = struct.unpack(f"<{n}f", data)
    need(all(map(math.isfinite, values)), "non-finite activation")
    return values


def segments(gate, up):
    finite(gate, K)
    finite(up, K)
    chunks = []
    for start in range(0, K * 4, N * 4):
        stop = start + N * 4
        chunks.append(gate[start:stop] + up[start:stop] + bytes((K - 2 * N) * 4))
    return chunks


def segment_output(raw):
    need(len(raw) == 3312, "dispatch extent")
    chunk = raw[: N * 4]
    finite(chunk, N)
    need(
        all(chunk[i : i + 4] != SENTINEL for i in range(0, len(chunk), 4)),
        "unwritten or ambiguous word",
    )
    need(raw[N * 4 :] == SENTINEL * 108, "activation tail overwrite")
    return chunk


def assemble(outputs):
    need(len(outputs) == 4, "four segments")
    return b"".join(segment_output(raw) for raw in outputs)


def f32_diff(gold, actual):
    lhs, rhs = finite(gold, K), finite(actual, K)
    aa, bb = struct.unpack("<2880I", gold), struct.unpack("<2880I", actual)

    def order(bits):
        return 0x80000000 - (bits & 0x7FFFFFFF) if bits >> 31 else 0x80000000 + bits

    changed = [i for i, (x, y) in enumerate(zip(aa, bb, strict=True)) if x != y]
    return dict(
        elements=K,
        changed_bits_words=len(changed),
        first=changed[0] if changed else None,
        changed_values=sum(x != y for x, y in zip(lhs, rhs, strict=True)),
        max_abs=max(abs(x - y) for x, y in zip(lhs, rhs, strict=True)),
        max_ulp=max(abs(order(x) - order(y)) for x, y in zip(aa, bb, strict=True)),
    )


def q_diff(a, b):
    need(len(a) == len(b) == 3060, "Q8 row width")
    scales, codes = [], []
    for j in range(90):
        start = 34 * j
        if a[start : start + 2] != b[start : start + 2]:
            scales.append(j)
        codes.extend(32 * j + i for i in range(32) if a[start + 2 + i] != b[start + 2 + i])
    return dict(
        scale_blocks=90,
        codes=2880,
        changed_scales=len(scales),
        first_scale_block=next(iter(scales), None),
        changed_codes=len(codes),
        first_code=next(iter(codes), None),
        same_input=not scales and not codes,
    )


def evaluate(cpu_f32, cpu_q8, gpu_f32, gpu_x4, arithmetic):
    quantize, unpack = arithmetic["quantize"], arithmetic["from_x4"]
    need(quantize(cpu_f32) == cpu_q8, "CPU SwiGLU/down Q8 bridge")
    projected, gpu_q8 = quantize(gpu_f32), unpack(gpu_x4)
    padding = gpu_x4[22 * 144 + 8 : 22 * 144 + 16] + gpu_x4[22 * 144 + 80 :]
    need(padding == bytes(72), "nonzero Q8 x4 padding")
    floats = f32_diff(cpu_f32, gpu_f32)
    effective = q_diff(cpu_q8, gpu_q8)
    decision = "DIFFERENT_EFFECTIVE_DOWN_OPERAND"
    if effective["same_input"]:
        decision = (
            "EQUAL_EFFECTIVE_DOWN_OPERAND_ONLY"
            if floats["changed_bits_words"]
            else "EQUAL_F32_AND_EFFECTIVE_DOWN_OPERAND"
        )
    return dict(
        decision=decision,
        f32=floats,
        activation_at_cpu_quantizer=q_diff(cpu_q8, projected),
        quantizer_on_gpu_activation=q_diff(projected, gpu_q8),
        end_to_end_q8=effective,
    )
