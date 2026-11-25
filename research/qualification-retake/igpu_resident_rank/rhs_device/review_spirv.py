"""Reproduce the optimized RHS data dependence in the physically dispatched module."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

DIGEST = "a988ec4090dca42f89a13de2ce43a69c376a0e79919e6f56875d4b1e0ab1ad25"

# (word address, SPIR-V opcode, operands). Addresses and result IDs belong to this module.
CHAIN = {
    599: (358, (61, 283, 100, 3, 281, 18)),  # clustered FMax, result %283
    606: (133, (61, 285, 283, 351)),  # FMul %283 * F32(1/127), output scale
    625: (136, (61, 290, 110, 283)),  # FDiv 127 / %283
    638: (245, (61, 345, 290, 288, 82, 291)),  # Phi: %290 or 0
    645: (142, (62, 296, 344, 345)),  # VectorTimesScalar input * %345
    650: (12, (62, 297, 1, 1, 296)),  # GLSL.std.450 Round
}


def inspect(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise ValueError("dispatched module SHA")
    words = struct.unpack(f"<{len(raw) // 4}I", raw)
    ops = {}
    constants = {}
    imports = {}
    i = 5
    while i < len(words):
        size, opcode = divmod(words[i], 65536)
        if not 0 < size <= len(words) - i:
            raise ValueError("instruction length")
        operands = words[i + 1 : i + size]
        ops[i] = (opcode, operands)
        if opcode == 43 and len(operands) == 3:
            constants[operands[1]] = operands[2]
        if opcode == 11:
            imports[operands[0]] = struct.pack(f"<{size - 2}I", *operands[1:]).split(b"\x00")[0]
        i += size
    if not all(ops.get(address) == instruction for address, instruction in CHAIN.items()):
        raise ValueError("unexpected rounding dataflow")
    if [constants[i] for i in (110, 351, 82)] != [0x42FE0000, 0x3C010204, 0]:
        raise ValueError("unexpected F32 constants")
    if imports[1] != b"GLSL.std.450":
        raise ValueError("unexpected rounding instruction set")
    return {
        "status": "REPRODUCED_OPTIMIZED_SPIRV",
        "sha256": DIGEST,
        "inverse_for_nonzero_max": "127.0 / max",
        "scale": "max * F32(1/127)",
        "word_offsets": list(CHAIN),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("module", type=Path)
    print(json.dumps(inspect(ap.parse_args().module), indent=2))
