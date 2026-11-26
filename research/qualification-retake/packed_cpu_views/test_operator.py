"""Build and run the synthetic C269 CPU-only MMID observation in a fresh directory."""

import argparse
import hashlib
import json
import resource
import struct
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOCOL = "ac66fd3429f281aba2f90e21228ca9702a2f07b16650815a736667d3705c40a9"
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
HEADERS = {
    "ggml.h": "98c5fcf96279e16c09d42dcba482be1b03434839db723bba4b65518e424ba181",
    "ggml-cpu.h": "1aafe97e576ea38c0da57517fb2492955d0b69c1a799842481fc069d6d9d28ef",
    "ggml-backend.h": "a620e815b43a44cc72d5f216629a3a91980335b61bc37eb6b2d0813368c3704f",
    "ggml-cpp.h": "bc15ba002c68685df23faae42df0d2b3d58032011f88b649021ab92485862c72",
    "ggml-alloc.h": "94e4cd069b9313b2ceb35dacec901981e0bb478d8bb31035b7126be091998c23",
    "gguf.h": "2ddb276a5bece743433160ad863279473431c9d4c171d468bf860a3cda3fbf3f",
}
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}
SLOTS = (39, 0, 7, 23, 7, 39, 23, 0, 23, 7, 0, 39)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def expected():
    out = bytearray()
    for k in range(3):
        for position in range(3):
            for rank in range(4):
                slot = SLOTS[4 * position + rank]
                for row in range(2880):
                    col = (row * 29 + slot * 67 + k * 347 + 31) % 2880
                    ch = rank if k == 1 else 0
                    value = (
                        127 if col % 32 == 0 else (col * 19 + position * 31 + ch * 37) % 223 - 111
                    )
                    signed = -value if (slot + row // 7 + k) % 2 else value
                    out += struct.pack("<f", signed)
    return bytes(out)


def verify_outputs(native, summary, libs):
    fields = summary.strip().split()
    require(len(fields) == 4 and fields[0] == "PASS", "MMID process output")
    count, stride_errors, component_errors = map(int, fields[1:])
    require(
        count == 3 * 3 * 4 * 2880 and 0 < stride_errors <= count and 0 < component_errors <= count,
        "missing mutation or output",
    )
    gold = expected()
    require(
        (native / "control.f32").read_bytes() == (native / "packed.f32").read_bytes() == gold,
        "independent oracle",
    )
    providers = (native / "providers.txt").read_text().splitlines()
    require(len(providers) == len(LIBS), "provider count")
    for location, name in zip(providers, LIBS, strict=True):
        path = Path(location)
        require(path.samefile(libs / name) and digest(path) == LIBS[name], "unexpected provider")
    return dict(
        finite_bitwise_values=count,
        output_sha256=hashlib.sha256(gold).hexdigest(),
        wrong_stride_mismatches=stride_errors,
        wrong_component_mismatches=component_errors,
        providers_sha256=LIBS,
        scheduler_backends=1,
        scheduler_splits=1,
        scheduler_pipeline_copies=1,
        mmids_per_graph=3,
        positions=3,
        top_k=4,
        slots=40,
        selected_distinct_slots=sorted(set(SLOTS)),
        stride_bytes=13_221_888,
    )


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
        cwd=root,
        text=True,
    ).strip()


def run(backend, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PRESERVED")
    try:
        require(not git(HERE, "status", "--porcelain"), "dirty measurement checkout")
        require(digest(HERE / "protocol.md") == PROTOCOL, "protocol digest")
        require(git(backend, "rev-parse", "HEAD") == PIN, "C269 pin")
        include = backend / "ggml/include"
        libs = backend / "build-c269-cuda/bin"
        for name, sha in HEADERS.items():
            require(digest(include / name) == sha, "header digest " + name)
        for name, sha in LIBS.items():
            require(digest(libs / name) == sha, "ELF digest " + name)
        receipt.update(
            commit=git(HERE, "rev-parse", "HEAD"),
            tree=git(HERE, "rev-parse", "HEAD^{tree}"),
            backend_commit=PIN,
            protocol_sha256=PROTOCOL,
            headers_sha256=HEADERS,
            program_sha256=digest(HERE / "operator.cpp"),
            runner_sha256=digest(Path(__file__)),
        )
        exe = out / "operator"
        cxx = Path("/usr/bin/g++")
        cmd = [
            str(cxx),
            "-std=c++17",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-pie",
            "-I" + str(include),
            str(HERE / "operator.cpp"),
            *(str(libs / name) for name in LIBS),
            "-ldl",
            "-o",
            str(exe),
        ]
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "LD_LIBRARY_PATH": str(libs),
            "OMP_NUM_THREADS": "2",
            "OMP_DYNAMIC": "FALSE",
        }
        with (out / "compile.log").open("wb") as log:
            subprocess.run(
                cmd, stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=100
            )
        receipt["compiler_sha256"] = digest(cxx)
        receipt["executable_sha256"] = digest(exe)
        native = out / "native"
        native.mkdir()
        with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
            subprocess.run(
                [str(exe), str(native)],
                stdout=stdout,
                stderr=stderr,
                env=env,
                check=True,
                timeout=120,
            )
        receipt.update(
            verify_outputs(native, (out / "stdout.txt").read_text(), libs),
            status="PASS_CPU_MMID_SYNTHETIC_PACKED_VIEWS",
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        receipt.update(
            error=type(exc).__name__, reason=str(exc) if isinstance(exc, ValueError) else None
        )
    receipt["child_maxrss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return int("error" in receipt)


class OperatorTests(unittest.TestCase):
    def test_reference_distinguishes_ranks_rows_and_components(self):
        data = expected()
        self.assertEqual(len(data), 3 * 3 * 4 * 2880 * 4)
        vectors = [data[i : i + 4 * 2880] for i in range(0, len(data), 4 * 2880)]
        self.assertEqual(len(set(vectors)), 36)

    def test_missing_negative_witness_is_rejected_before_reading_files(self):
        with self.assertRaisesRegex(ValueError, "mutation"):
            verify_outputs(None, "PASS 103680 0 400", None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.backend.resolve(strict=True), args.new_output_dir.resolve()))
