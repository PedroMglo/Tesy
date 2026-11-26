"""Wire oracle for the two pre-registered Q8_1 x4 predictions (C269, 8234bfb6).

The inputs are binary32 words. A physical x4 record has four little-endian
(scale, scaled sum) binary16 pairs followed by four consecutive 32-byte i8
blocks. The shader scales the integer sum with binary32 d before storing
binary16. The second prediction substitutes only the CPU code at v and
recomputes the dependent sum; Q8_0 itself has no sum field.
"""

import hashlib
import struct

K = 2880
BLOCK = 32
STRIDE = 144
OUTPUT_BYTES = 23 * STRIDE
LITERAL = "LITERAL_Q8_1_1_2"
CPU = "CPU_CODES_2_2"


def inputs():
    words = [0] * K
    words[0:2] = [0x41300000, 0x3E050A14]
    words[32:34] = [0x41300000, 0x3E400000]
    words[64:66] = [0x42FE0000, 0xC0400000]
    return struct.pack("<2880I", *words)


def _f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _output(first_code):
    # The maximum coefficient quantizes to 127 in all three active blocks.
    encoded = bytearray(OUTPUT_BYTES)
    for block, (maximum, other_code) in enumerate(((11, first_code), (11, 2), (127, -3))):
        base, lane = divmod(block, 4)
        d = _f32(maximum / 127)
        scaled_sum = _f32((127 + other_code) * d)
        struct.pack_into("<ee", encoded, STRIDE * base + 4 * lane, d, scaled_sum)
        struct.pack_into("<bb", encoded, STRIDE * base + 16 + BLOCK * lane, 127, other_code)
    return bytes(encoded)


def grade(raw):
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise ValueError("expected raw x4 bytes")
    raw = bytes(raw)
    if len(raw) != OUTPUT_BYTES:
        raise ValueError(f"expected {OUTPUT_BYTES} x4 bytes, received {len(raw)}")
    models = {LITERAL: _output(1), CPU: _output(2)}
    verdict = next((name for name, expected in models.items() if expected == raw), None)
    if verdict is None:
        differences = {}
        for name, expected in models.items():
            differences[name] = next(
                i for i, pair in enumerate(zip(raw, expected, strict=True)) if pair[0] != pair[1]
            )
        raise ValueError(f"outside both x4 models; first byte offsets {differences}")
    headers = list(struct.iter_unpack("<HH", raw[:12]))
    return {
        "verdict": verdict,
        "decision": (
            "CLOSE_BITWISE_RHS_FOR_THIS_SHADER"
            if verdict == LITERAL
            else "GO_COMPARE_REAL_PROJECTION"
        ),
        "codes": [raw[17], raw[49]],
        "scale_f16_bits": [f"{scale:04x}" for scale, _ in headers],
        "sum_f16_bits": [f"{total:04x}" for _, total in headers],
        "input_sha256": hashlib.sha256(inputs()).hexdigest(),
        "output_sha256": hashlib.sha256(raw).hexdigest(),
        "expected_sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in models.items()
        },
        "output_bytes": len(raw),
    }
