"""Reconstruct the C269 AVX2 MXFP4 x Q8_0 arithmetic, before bias."""

import ctypes
import math
import struct

K = 2880
BLOCKS = K // 32
WROW = BLOCKS * 17
QROW = BLOCKS * 34
LEVELS = (0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12)
F32 = struct.Struct("<f")
HALF = struct.Struct("<e")
FMA = ctypes.CDLL("libm.so.6").fmaf
FMA.argtypes = [ctypes.c_float] * 3
FMA.restype = ctypes.c_float


def f32(value):
    return F32.unpack(F32.pack(value))[0]


def quantize(data):
    if len(data) != K * 4:
        raise ValueError("input width")
    out = bytearray()
    values = struct.unpack("<2880f", data)
    if not all(map(math.isfinite, values)):
        raise ValueError("non-finite activation")
    for pos in range(0, K, 32):
        block = values[pos : pos + 32]
        amax = max(map(abs, block))
        d = f32(amax / 127)
        inverse = f32(127 / amax) if amax else 0
        codes = [round(f32(value * inverse)) for value in block]
        out.extend(struct.pack("<e32b", d, *codes))
    return bytes(out)


def unpack_q8(q8):
    if len(q8) != QROW:
        raise ValueError("Q8_0 width")
    blocks = list(struct.iter_unpack("<e32b", q8))
    if any(not math.isfinite(block[0]) or block[0] < 0 for block in blocks):
        raise ValueError("non-finite or negative Q8 scale")
    return blocks


def from_x4(data):
    if len(data) != 23 * 144:
        raise ValueError("Q8_1 x4 width")
    out = bytearray()
    for b in range(BLOCKS):
        outer, lane = divmod(b, 4)
        ds = 144 * outer + 4 * lane
        code = 144 * outer + 16 + 32 * lane
        out.extend(data[ds : ds + 2])  # ds.y and the two padding lanes do not enter MXFP4.
        out.extend(data[code : code + 32])
    return bytes(out)


def dot_row(weight, activation, *, trace=False):
    # Activation block layout is (FP16 scale as float, followed by 32 signed bytes).
    if len(weight) != WROW or len(activation) != BLOCKS:
        raise ValueError("dot geometry")
    acc = [[0.0] * 8, [0.0] * 8]
    trace_rows = []
    for block, (exp, *packed) in enumerate(struct.iter_unpack("<17B", weight)):
        scale_y, *codes = activation[block]
        scale = f32(math.ldexp(scale_y, exp - 128))
        low = [LEVELS[nibble & 15] for nibble in packed]
        high = [LEVELS[nibble >> 4] for nibble in packed]
        products = []
        for level, code in zip(low + high, codes, strict=True):
            # VPSIGNB negates in i8, including wrap at -128. VMADDUBS cannot saturate here.
            product = level * code
            products.append(-product if level < 0 and code == -128 else product)
        lanes = [sum(products[i : i + 4]) for i in range(0, 32, 4)]
        parity = block % 2
        for i, subtotal in enumerate(lanes):
            acc[parity][i] = FMA(scale, subtotal, acc[parity][i])
        if trace:
            trace_rows.append((block, exp, lanes, [F32.pack(v).hex() for v in acc[parity]]))
    result = [f32(a + b) for a, b in zip(*acc, strict=True)]
    # VEXTRACTF128 + ADDPS, MOVEHL + ADDPS, MOVEHDUP + ADDSS.
    four = [f32(result[i + 4] + result[i]) for i in range(4)]
    two = [f32(four[i] + four[i + 2]) for i in range(2)]
    return F32.pack(f32(two[0] + two[1])), trace_rows


def project(weights, q8):
    blocks = unpack_q8(q8)
    memory = memoryview(weights)
    if len(memory) != WROW * K:
        raise ValueError("matrix geometry")
    return b"".join(
        dot_row(memory[pos : pos + WROW], blocks)[0] for pos in range(0, len(memory), WROW)
    )
