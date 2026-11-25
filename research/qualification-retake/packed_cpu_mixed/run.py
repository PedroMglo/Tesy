"""Authenticated C269 mixed-scheduler synthetic fixture, under external hardware supervision."""

import argparse
import hashlib
import json
import resource
import subprocess
import sys
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from packed_cpu_views import test_direct_io as dio  # noqa: E402
from packed_cpu_views import test_operator as cpu  # noqa: E402

PROTOCOL = "8bd267ff7756ddf54684c459f4f64544ce833692e6a8cc2bfdee0e1771f1df23"
FROZEN = {
    "operator.cpp": "8bba9315cb8647f42e1cae68b5384195f67f5aa3f55f4ec9946cd28d1aa4ec23",
    "test_operator.py": "1fd218dc882717c4a877bdfbe519401749d00cf5e5eeab99e68ef8d980e74031",
    "test_direct_io.py": "c97ad4daa175b2f14c3532b1f968e47a6d04978da7bac356a1caf65a12b26d63",
}
LIBS = {
    **cpu.LIBS,
    "libggml-cuda.so.0.15.3": "ff43655b15df5f3de1d5e00b0da18469a14f118bd644eb4b6d7f1915c85a4493",
}
HEADERS = {
    **cpu.HEADERS,
    "ggml-cuda.h": "84122bf381c24709eab9e888034956eafc1dfe436f9d826c10fa0e1a695f8a5e",
}
require = cpu.require


def prerequisite(path, sha):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, "prerequisite digest")
    return json.loads(data)


def route(n, p, r):
    return 34 + r if n == 3 and r >= 2 else (39, 0, 7, 23)[(r + p) % 4]


def verify_native(out, libs):
    scopes = {}
    summary = (out / "stdout.txt").read_text().splitlines()
    require(len(summary) == 3, "wrong graph count")
    for n, line in zip((1, 32, 3), summary, strict=True):
        fields = line.split()
        require(len(fields) == 5 and fields[0] == "PASS", "incomplete split observation")
        size, dense, packed, count = map(int, fields[1:])
        require(
            n == size and min(dense, packed) >= 3 and count == 3 * n * 4 * 2880,
            "mixed graph or coverage",
        )
        path = out / "native" / f"{n}.f32"
        require(
            path.stat().st_size == 2 * count * 4 and sys.byteorder == "little",
            "output size or endian",
        )
        values = array("f")
        with path.open("rb") as source:
            values.fromfile(source, 2 * count)
        i = 0
        for k in range(3):
            for p in range(n):
                for r in range(4):
                    slot = route(n, p, r)
                    ch = r if k == 1 else 0
                    for y in range(2880):
                        col = (29 * y + 67 * slot + 347 * k + 31) % 2880
                        x = 127 if col % 32 == 0 else (19 * col + 31 * p + 37 * ch) % 223 - 111
                        gold = -x if (slot + y // 7 + k) % 2 else x
                        require(
                            values[i] == gold
                            and values[count + i] == (0 if n == 3 and r >= 2 else gold),
                            "independent mixed numeric or parking mask",
                        )
                        i += 1
        scopes[n] = dict(
            position_count=n,
            raw_and_masked_values_each=count,
            dense_splits=dense,
            packed_splits=packed,
            result_sha256=cpu.digest(path),
            cpu_weight_operand_witnesses_per_layout=3,
            cuda_to_cpu_activation_and_id_edges_per_layout=6,
            cpu_to_cuda_output_edges_per_layout=3,
        )
    paths = (out / "native/providers.txt").read_text().splitlines()
    for name, p in zip(LIBS, paths, strict=True):
        require(
            Path(p).samefile(libs / name) and cpu.digest(Path(p)) == LIBS[name],
            "mapped GGML provider",
        )
    return scopes


def main(args):
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PRESERVED")
    try:
        require(not cpu.git(HERE, "status", "--porcelain"), "dirty checkout")
        require(cpu.digest(HERE / "contract.md") == PROTOCOL, "protocol")
        for name, pin in FROZEN.items():
            require(cpu.digest(HERE.parent / "packed_cpu_views" / name) == pin, "frozen fixture")
        before = prerequisite(args.cpu_receipt, args.cpu_sha256)
        require(
            before["status"] == "PASS_CPU_MMID_SYNTHETIC_PACKED_VIEWS"
            and before["program_sha256"] == FROZEN["operator.cpp"]
            and before["finite_bitwise_values"] == 103680
            and before["providers_sha256"] == cpu.LIBS
            and min(before["wrong_component_mismatches"], before["wrong_stride_mismatches"]) > 0,
            "CPU gate",
        )
        io = dio.verify(prerequisite(args.io_receipt, args.io_sha256), True)
        require(io["status"] == "PASS_BTRFS_NVME_DIRECT_FIXTURE", "physical direct I/O gate")
        backend = args.backend.resolve(strict=True)
        require(cpu.git(backend, "rev-parse", "HEAD") == cpu.PIN, "C269 pin")
        include = backend / "ggml/include"
        libs = backend / "build-c269-cuda/bin"
        for name, pin in HEADERS.items():
            require(cpu.digest(include / name) == pin, "header " + name)
        for name, pin in LIBS.items():
            require(cpu.digest(libs / name) == pin, "ELF " + name)
        receipt.update(
            commit=cpu.git(HERE, "rev-parse", "HEAD"),
            tree=cpu.git(HERE, "rev-parse", "HEAD^{tree}"),
            protocol_sha256=PROTOCOL,
            program_sha256=cpu.digest(HERE / "mixed.cpp"),
            runner_sha256=cpu.digest(Path(__file__)),
            prerequisite_sha256={"cpu": args.cpu_sha256, "io": args.io_sha256},
            backend_commit=cpu.PIN,
            headers_sha256=HEADERS,
            providers_sha256=LIBS,
        )
        cxx = Path("/usr/bin/g++")
        exe = out / "mixed"
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
            str(HERE / "mixed.cpp"),
            *(str(libs / name) for name in LIBS),
            "-ldl",
            "-o",
            str(exe),
        ]
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "OMP_NUM_THREADS": "2",
            "OMP_DYNAMIC": "FALSE",
            "LD_LIBRARY_PATH": str(libs),
            "CUDA_VISIBLE_DEVICES": "0",
            "CUDA_CACHE_DISABLE": "1",
        }
        with (out / "compile.log").open("wb") as log:
            subprocess.run(
                cmd, stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=60
            )
        receipt.update(compiler_sha256=cpu.digest(cxx), executable_sha256=cpu.digest(exe))
        (out / "native").mkdir()
        with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
            subprocess.run(
                [str(exe), str(out / "native")],
                stdout=stdout,
                stderr=stderr,
                env=env,
                check=True,
                timeout=150,
            )
        receipt.update(
            scopes=verify_native(out, libs), status="PASS_C269_MIXED_PACKED_MMID_POINTERS"
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        receipt.update(
            error=type(exc).__name__, reason=str(exc) if isinstance(exc, ValueError) else None
        )
    receipt["child_maxrss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return int("error" in receipt)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for option in ("backend", "cpu-receipt", "io-receipt", "new-output-dir"):
        p.add_argument("--" + option, type=Path, required=True)
    p.add_argument("--cpu-sha256", required=True)
    p.add_argument("--io-sha256", required=True)
    raise SystemExit(main(p.parse_args()))
