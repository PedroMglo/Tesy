"""Build a tiny driver from the pinned stock source, or check one device in a new output."""

import argparse
import hashlib
import json
import os
import re
import resource
import struct
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
CACHE_SOURCE = "721355f5d9d1d54f9fe802279cb10964c82352168ca6b359ccdbb02af39c1a8a"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def libraries(exe, libs, known):
    ld = subprocess.check_output(["ldd", exe], text=True, timeout=5)
    require("not found" not in ld, "unresolved library")
    result = {}
    for name, file in re.findall(r"^\s*(libggml\S+) => (\S+) \(", ld, re.M):
        path = Path(file).resolve()
        digest = sha(path)
        require(path.parent == libs.resolve() and digest == known[name], "stock DSO binding")
        result[name] = digest
    require(
        {"libggml-base.so.0", "libggml-cuda.so.0", "libggml-cpu.so.0"} <= set(result),
        "missing backend",
    )
    return result


def build(a, receipt, result):
    src = a.stock / "source"
    require(
        subprocess.check_output(["git", "-C", src, "rev-parse", "HEAD"]).decode().strip() == PIN
        and not subprocess.check_output(["git", "-C", src, "status", "--porcelain"]),
        "clean pin",
    )
    upstream = src / "src/llama-moe-cache.cpp"
    require(sha(upstream) == CACHE_SOURCE, "source SHA")
    code = upstream.read_bytes()
    planner = (
        code[code.index(b"struct moe_cache_lru {") : code.index(b"\n// gate, up, down")].strip()
        + b"\n"
    )
    extraction = a.new_output / "sealed-planner.inc"
    extraction.write_bytes(planner)
    compiler = Path("/usr/bin/g++-15")
    require(sha(compiler) == receipt["toolchain"]["cxx"]["sha256"], "compiler SHA")
    libs = a.stock / "build/bin"
    exe = a.new_output / "operator"
    args = [
        compiler,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I" + str(src / "ggml/include"),
        "-I" + str(a.new_output),
        HERE / "operator.cpp",
        "-L" + str(libs),
        "-Wl,-rpath," + str(libs),
        "-lggml-cpu",
        "-lggml-cuda",
        "-lggml-base",
        "-o",
        exe,
    ]

    def clamp():
        resource.setrlimit(resource.RLIMIT_AS, (650 * 2**20,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 2**20,) * 2)

    with (a.new_output / "build.log").open("xb") as f:
        subprocess.run(
            args,
            timeout=60,
            check=True,
            preexec_fn=clamp,
            stdout=f,
            stderr=subprocess.STDOUT,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(a.new_output)},
        )
    result.update(
        status="PASS_BUILD",
        executable_sha256=sha(exe),
        compiler_sha256=sha(compiler),
        planner_sha256=sha(extraction),
        stock_planner_source_sha256=CACHE_SOURCE,
        libraries=libraries(exe, libs, receipt["own_libs_sha256"]),
    )


def execute(a, receipt, result):
    identity = json.loads((a.build / "receipt.json").read_text())
    exe = a.build / "operator"
    require(
        identity["status"] == "PASS_BUILD"
        and identity["executable_sha256"] == sha(exe)
        and all(
            identity[key] == result[key]
            for key in ("source_sha256", "stock_receipt_sha256", "protocol_sha256", "runner_sha256")
        ),
        "build receipt",
    )
    libs = a.stock / "build/bin"
    require(libraries(exe, libs, receipt["own_libs_sha256"]) == identity["libraries"], "DSO drift")
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(libs),
        "CUDA_VISIBLE_DEVICES": "" if a.mode == "CPU" else "0",
    }
    vectors = a.new_output / "vectors.f32"
    log = a.new_output / "operator.log"

    def runtime_limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 2**20,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with log.open("xb") as f:
        subprocess.run(
            [exe, a.mode, vectors],
            env=env,
            timeout=30,
            preexec_fn=runtime_limits,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
        )
    lines = log.read_text().splitlines()
    devices = [line[7:] for line in lines if line.startswith("DEVICE ")]
    require(len(devices) == 1 and devices[0].startswith(a.mode), "backend name")
    plans = []
    with vectors.open("rb") as stream:
        for line in lines:
            if not line.startswith("PLAN "):
                continue
            call, layer, tokens, unique, hits, fills, evicted, reloaded, stride, count = (
                int(v) for v in line.split()[1:]
            )
            index = len(plans)
            require(
                (call, layer) == divmod(index, 2)
                and tokens == (16, 1, 1)[call]
                and count == 64 * 4 * tokens
                and unique == hits + fills,
                "plan dimensions",
            )
            outputs = [stream.read(4 * count) for _ in range(3)]
            require(
                len(outputs[0]) == 4 * count and outputs[0] == outputs[1] == outputs[2],
                "three finite ordered outputs",
            )
            require(
                all(abs(v[0]) < float("inf") for v in struct.iter_unpack("<f", outputs[0])),
                "nonfinite",
            )
            plans.append(
                dict(
                    call=call,
                    layer=layer,
                    tokens=tokens,
                    selected=unique,
                    hits=hits,
                    fills=fills,
                    evictions=evicted,
                    reloaded=reloaded,
                    reuse_payload_bytes=fills * stride,
                    recopy_payload_bytes=unique * stride,
                    output_values=count,
                    output_sha256=hashlib.sha256(outputs[0]).hexdigest(),
                )
            )
        require(len(plans) == 6, "six plans")
        corrupt = stream.read(4 * count)
        require(
            len(corrupt) == 4 * count and corrupt != outputs[0] and not stream.read(1),
            "wrong-ID discriminator or trailing data",
        )
    result.update(
        status="PASS_" + a.mode + "_NATIVE_OPERATOR",
        backend=devices[0],
        executable_sha256=identity["executable_sha256"],
        plans=plans,
        build_sha256=sha(a.build / "receipt.json"),
        vectors_sha256=sha(vectors),
        wrong_id_control_sha256=hashlib.sha256(corrupt).hexdigest(),
    )


def main(a):
    os.umask(0o077)
    a.new_output.mkdir(exist_ok=False)
    receipt = json.loads(a.stock_receipt.read_text())
    result = dict(
        status="FAIL",
        pin=PIN,
        source_sha256=sha(HERE / "operator.cpp"),
        runner_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        stock_receipt_sha256=sha(a.stock_receipt),
    )
    now = time.monotonic()
    try:
        require(
            receipt["decision"] == "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI" and receipt["pin"] == PIN,
            "stock build",
        )
        if a.mode == "build":
            build(a, receipt, result)
        else:
            require(a.build is not None, "build path")
            execute(a, receipt, result)
    except Exception as e:
        result.update(reason=type(e).__name__)
        raise
    finally:
        result.update(
            elapsed_s=round(time.monotonic() - now, 4),
            max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        )
        result["raw_sizes"] = {p.name: p.stat().st_size for p in a.new_output.iterdir()}
        tmp = a.new_output / ".pending"
        tmp.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        tmp.rename(a.new_output / "receipt.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "CPU", "CUDA"))
    for key in ("stock", "stock-receipt", "new-output", "build"):
        p.add_argument("--" + key, type=Path, required=key != "build")
    main(p.parse_args())
