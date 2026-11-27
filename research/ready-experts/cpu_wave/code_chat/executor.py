"""Compare the unmodified expert GEMV of a separate C engine with R0's GGUF weight order."""

import argparse
import ctypes as ct
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
METHOD = "a485c140f744eb58855462c11c18d6f54f118fef87f02ee4a83864483c76958f"
UPSTREAM = "9570410cab7e34bf7ac044559fc56dcdf4c7c195"
SOURCES = {
    "include/dequant.h": "50ae4188da18908012c28e4df45a38d74ff867d8aebefb602a8293a72dc6c7c0",
    "include/types.h": "8222121ba3e8cdd3adf29c3af1dcceb187638d84e7efe2b30093e05eb57211d1",
    "src/dequant.c": "313c88d53fcde8bf3fd9018e1366c4532f4df2a8e1703b7dabb4cc72758ca4ad",
    "src/transformer.c": "7faad33a700453bc83c4d048a3ea729eca8767029fc7eb64e2750f9d6b9ebcae",
}
REFERENCE = "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539"
C291 = "cd4c0665c5485268cddfc7dba576b1cf490222c120cf34f72d555a6cbccbc5b9"
F32 = ct.c_float * 64
U8 = ct.c_uint8 * 34
FLOAT_PTR = ct.POINTER(ct.c_float)
BYTE_PTR = ct.POINTER(ct.c_uint8)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def fixture():
    nibbles = bytes(((15 - j) << 4) | j for j in range(16))
    return {
        "constant": (bytes([127]) + bytes([0x22]) * 16) * 2,
        "distinct": bytes([127]) + nibbles + bytes([128]) + nibbles,
    }


def original(folder):
    receipt = (folder / "receipt.json").read_bytes()
    require(sha(receipt) == C291, "C291 placement")
    identity = json.loads(receipt)
    index = (folder / "integral-index.json").read_bytes()
    require(sha(index) == identity["index_sha256"], "C291 expert index")
    first = json.loads(index)["experts"][0]
    component = first["components"][0]
    require(
        (
            first["layer"],
            first["expert"],
            component["name"],
            component["type"],
            component["size_bytes"],
        )
        == (0, 0, "blk.0.ffn_gate_exps.weight", "mxfp4", 4406400),
        "first gate slab",
    )
    with Path(identity["model_path"]).open("rb", buffering=0) as stream:

        def check_fd():
            st = os.fstat(stream.fileno())
            require(
                dict(
                    dev=st.st_dev,
                    inode=st.st_ino,
                    size_bytes=st.st_size,
                    mtime_ns=st.st_mtime_ns,
                    ctime_ns=st.st_ctime_ns,
                )
                == identity["model_stat"],
                "GGUF descriptor changed",
            )

        check_fd()
        data = os.pread(stream.fileno(), component["size_bytes"], component["source_offset"])
        require(sha(data) == component["sha256"], "qualified gate payload")
        check_fd()
    return data[:34], dict(
        model_sha256=identity["model_sha256"],
        tensor=component["name"],
        expert=first["expert"],
        file_offset=component["source_offset"],
        model_logical_bytes_read=len(data),
        slab_sha256=component["sha256"],
    )


def compare(expected, actual):
    require(
        len(expected) == len(actual) == 64 and all(math.isfinite(x) for x in [*expected, *actual]),
        "64 finite basis coordinates",
    )
    mismatch = [i for i, (x, y) in enumerate(zip(expected, actual, strict=True)) if x != y]
    return dict(
        values=64,
        numerical_mismatches=len(mismatch),
        first_mismatch=mismatch[0] if mismatch else None,
        output_f32_sha256=sha(bytes(actual)),
    )


def basis_products(dot, encoded, *, permute):
    products = F32()
    for i in range(64):
        basis = F32()
        index = 32 * (i // 32) + 2 * (i % 16) + (i % 32) // 16 if permute else i
        basis[index] = 1.0
        value = ct.c_float()
        dot(encoded, basis, ct.byref(value), 1, 64)
        products[i] = value.value
    return products


def run(args, out):
    require(sha((HERE / "executor.md").read_bytes()) == METHOD, "prior protocol")
    for name, ref in SOURCES.items():
        require(sha((args.source / name).read_bytes()) == ref, "upstream source " + name)
    require(sha(args.reference.read_bytes()) == REFERENCE, "independent R0 decoder")
    rows = fixture()
    rows["first_real_gate"], provenance = original(args.derived)
    ref = ct.CDLL(str(args.reference)).dequantize_row_mxfp4
    ref.argtypes = [BYTE_PTR, FLOAT_PTR, ct.c_int64]
    ref.restype = None
    expected = {}
    for name, data in rows.items():
        values = F32()
        ref(U8.from_buffer_copy(data), values, 64)
        expected[name] = values
    require(
        list(expected["constant"]) == [1.0] * 64
        and list(expected["distinct"])[:3] == [0.0, 0.5, 1.0]
        and expected["distinct"][16] == -6.0,
        "independent control values",
    )
    flags = [
        "-O2",
        "-std=gnu11",
        "-fno-fast-math",
        "-g0",
        "-fPIC",
        "-shared",
        "-Wl,--build-id=none",
    ]
    cases = {}
    for name, cpu in (("scalar", ["-mno-avx2"]), ("avx2", ["-mavx2", "-mfma", "-mf16c"])):
        dest = out / (name + ".so")
        cmd = [
            "/usr/bin/gcc",
            *flags,
            *cpu,
            "-I",
            str(args.source / "include"),
            str(args.source / "src/dequant.c"),
            "-lm",
            "-o",
            str(dest),
        ]
        subprocess.run(cmd, check=True, timeout=30, capture_output=True)
        lib = ct.CDLL(str(dest))
        vector = lib.dequant_mxfp4_row
        vector.argtypes = [BYTE_PTR, FLOAT_PTR, ct.c_uint32]
        vector.restype = None
        dot = lib.gemv_mxfp4_f32_direct
        dot.argtypes = [BYTE_PTR, FLOAT_PTR, FLOAT_PTR, ct.c_uint32, ct.c_uint32]
        dot.restype = None
        result = {}
        for key, data in rows.items():
            encoded = U8.from_buffer_copy(data)
            decoded = F32()
            vector(encoded, decoded, 64)
            result[key] = dict(
                row=compare(expected[key], decoded),
                gemv=compare(expected[key], basis_products(dot, encoded, permute=False)),
                gemv_permuted_input=compare(
                    expected[key], basis_products(dot, encoded, permute=True)
                ),
            )
        require(
            all(v["numerical_mismatches"] == 0 for v in result["constant"].values()),
            "constant one-hot control",
        )
        cases[name] = dict(flags=flags + cpu, binary_sha256=sha(dest.read_bytes()), cases=result)
    if any(
        case["cases"]["first_real_gate"]["gemv"]["numerical_mismatches"] for case in cases.values()
    ):
        decision = "NO_GO_AS_SHIPPED_EXPERT_GEMV"
    elif all(
        check["numerical_mismatches"] == 0
        for case in cases.values()
        for row in case["cases"].values()
        for check in (row["row"], row["gemv"])
    ):
        decision = "GO_ROUTED_LAYER_ONLY"
    else:
        decision = "INCONCLUSIVE"
    return dict(
        decision=decision,
        classification="MEDIDO_OPERADOR_CPU",
        upstream_commit=UPSTREAM,
        protocol_sha256=METHOD,
        program_sha256=sha(Path(__file__).read_bytes()),
        source_sha256=SOURCES,
        reference_sha256=REFERENCE,
        c291_receipt_sha256=C291,
        compiler_sha256=sha(Path("/usr/bin/gcc").read_bytes()),
        input_sha256={k: sha(v) for k, v in rows.items()},
        reference_f32_sha256={k: sha(bytes(v)) for k, v in expected.items()},
        builds=cases,
        provenance=provenance,
        full_model_forwards=0,
        gpu_forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "derived", "reference", "new-output-dir"):
        parser.add_argument("--" + key, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir()
    try:
        result = run(args, out)
    except Exception as exc:
        with (out / "failure.json").open("x") as dest:
            json.dump(dict(status="FAIL_PRESERVED", reason=str(exc)), dest, indent=2)
        raise
    with (out / "decision.json").open("x") as dest:
        json.dump(result, dest, sort_keys=True, indent=2, allow_nan=False)
        dest.write("\n")
    print(result["decision"])
