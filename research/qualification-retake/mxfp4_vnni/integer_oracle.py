"""Check each possible nibble/Q8 byte against an independent one-lane result."""

import argparse
import ctypes
import hashlib
import json
import os
import struct
from pathlib import Path

from build_native import R0_SHA, SYMBOL, require, sha

LEVELS = (0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12)


def fixtures():
    for tail in (False, True):
        blocks = 3 if tail else 2
        for nibble, level in enumerate(LEVELS):
            for q in range(-128, 128):
                # Select each of the 32 lanes across this exhaustive fixture.
                lane = (q + nibble) % 32
                block = 2 if tail else (q & 1)
                w = bytearray(bytes([128] + [0] * 16) * blocks)  # E8M0/2 = 1
                y = bytearray(bytes([0, 0x3C] + [0] * 32) * blocks)  # f16 = 1
                w[17 * block + 1 + lane % 16] = nibble << (4 if lane >= 16 else 0)
                y[34 * block + 2 + lane] = q & 255
                expected = level * q
                if not tail and level < 0 and q == -128:
                    # VPSIGNB negation wraps in int8. The odd scalar tail uses int.
                    expected = -expected
                yield blocks * 32, bytes(w), bytes(y), struct.pack("<f", expected)


def check(r0, build):
    receipt = json.loads((build / "build.json").read_text())
    require(receipt["status"] == "PASS_BUILD_DISASSEMBLY_ONLY", "build status")
    require(sha(r0) == R0_SHA, "R0 digest")
    root = ctypes.CDLL(r0, mode=os.RTLD_NOW | os.RTLD_GLOBAL)
    root.ggml_cpu_init.argtypes = []
    root.ggml_cpu_init.restype = None
    root.ggml_cpu_init()
    names = ("r0", "control", "candidate", "fallback")
    libraries = [root]
    for name in names[1:]:
        path = build / (name + ".so")
        require(sha(path) == receipt["arms"][name]["sha256"], f"{name} digest")
        libraries.append(ctypes.CDLL(path, mode=os.RTLD_NOW | os.RTLD_LOCAL))
    dots = [getattr(library, SYMBOL) for library in libraries]
    for dot in dots:
        dot.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_int,
        ]
        dot.restype = None
    count = 0
    digest = hashlib.sha256()
    for n, w, y, expected in fixtures():
        for name, dot in zip(names, dots, strict=True):
            value = ctypes.c_float(float("nan"))
            dot(n, ctypes.byref(value), 0, w, 0, y, 0, 1)
            require(bytes(value) == expected, f"{name} mismatch at row {count}, n={n}")
        count += 1
        digest.update(expected)
    return {
        "status": "PASS_INDEPENDENT_INTEGER_ORACLE",
        "rows": count,
        "implementations": names,
        "gold_f32le_sha256": digest.hexdigest(),
        "build_receipt_sha256": sha(build / "build.json"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r0", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    with args.out.open("x") as output:
        try:
            result = check(args.r0, args.build)
        except (OSError, ValueError, KeyError) as exc:
            json.dump({"status": "FAIL", "error": str(exc)}, output)
            raise
        output.write(json.dumps(result, indent=2) + "\n")
        print(result["status"], result["rows"])
