"""Build the true CPU-buffer variant, retaining the qualified RADV launcher and shader."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "rank_radv"
P = run_path(OLD / "build.py")
B = P["B"]
BASE, sha, need, save = (B[k] for k in ("BASE", "sha", "need", "save"))
PROTO = "1b3e258a0208e1406b1403bb76db3637a5cbf3ae8708554f8861f96a11110980"
PRIOR = "e68f5df23021e1e732d5dc17e68be33f973edeefb6170f56df9e1d183cfe3c48"
PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
DSOS = {
    "base": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
    "cpu": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
}


def inputs():
    need(sha(HERE / "protocol.md") == PROTO, "primary protocol")
    return dict(
        predecessor=P["pins"](),
        sources={n: sha(HERE / n) for n in ("build.py", "primary.inc", "run.py", "protocol.md")},
    )


def generate(out):
    P["generate"](out)
    src = (OLD / "backing.inc").read_text().split("void identify_vma(", 1)[0]
    (out / "records.inc").write_text(B["replace"](src, "{24,7,318210048", "{24,6,318210048"))
    file = out / "projection.inc"
    s = file.read_text()
    s = B["replace"](s, '#include "backing.inc"', '#include "primary.inc"')
    a = s.index("        if(cache.record->generation")
    b = s.index("        vk(vkWaitForFences", a)
    s = s[:a] + s[b:]
    a = s.index('        std::printf("role_result')
    b = s.index("    vkDestroyFence", a)
    s = s[:a] + s[b:]
    a = s.index("    need(cache.publish(")
    b = s.index("    vkDestroyPipeline(p.dev,pipeline", a)
    s = (
        s[:a]
        + """    cache.select(0);emit(0,args[7]);cache.release_after_fence();
    emit(2,args[8]);cache.release_after_fence();
    cache.select(1);emit(0,args[9]);cache.release_after_fence();cache.cleanup();
"""
        + s[b:]
    )
    file.write_text(s)
    file = out / "dispatch.cpp"
    file.write_text(
        B["replace"](file.read_text(), "PASS_RANK_BACKING_DISPATCH", "PASS_PRIMARY_CPU_IMPORT")
    )


def libs(backend):
    d = backend / "build-c269-cuda/bin"
    native = {k: (d / f"libggml-{k}.so.0.15.3").resolve(strict=True) for k in DSOS}
    need(all(sha(p) == DSOS[k] for k, p in native.items()), "C269 CPU/base")
    return native


def build(a, out):
    inc = a.backend / "ggml/include"
    native = libs(a.backend)
    need(
        subprocess.check_output(
            ["git", "-C", str(a.backend), "rev-parse", "HEAD"], text=True
        ).strip()
        == PIN,
        "C269",
    )
    headers = {}
    for n in ("ggml.h", "ggml-alloc.h", "ggml-cpu.h", "ggml-backend.h", "ggml-cpp.h"):
        payload = subprocess.check_output(
            ["git", "-C", str(a.backend), "show", PIN + ":ggml/include/" + n]
        )
        need(payload == (inc / n).read_bytes(), "C269 GGML header " + n)
        headers[n] = sha(inc / n)
    need(all(sha(a.headers / "vulkan" / n) == h for n, h in B["HEADERS"].items()), "Vulkan headers")
    need(sha(a.previous_dir / "receipt.json") == PRIOR, "prior build")
    generate(out)
    for n, digest in (
        ("gate.spv", P["ORDERED_SPV"]),
        ("subgroup.spv", P["RHS_SPV"]),
        ("shared.spv", "492cb6c575235e79f20bdc667491480e698730f0533cdb00ea64342d341bb3d6"),
    ):
        need(sha(a.previous_dir / n) == digest, "previous shader")
        shutil.copyfile(a.previous_dir / n, out / n)
    defines = [f'-D{k.upper()}_DSO="{path}"' for k, path in native.items()]
    args = [
        str(BASE["CXX"]),
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-missing-field-initializers",
        *defines,
        "-I",
        str(inc),
        "-I",
        str(a.headers),
        "-I",
        str(HERE),
        "-I",
        str(P["STOCK"]),
        "-I",
        str(out),
        str(out / "dispatch.cpp"),
        str(native["cpu"]),
        str(native["base"]),
        str(BASE["LOADER"]),
        str(B["CRYPTO"]),
        "-Wl,-rpath," + str(native["cpu"].parent),
        "-o",
        str(out / "rank"),
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    return dict(
        status="PASS_PRIMARY_BUILD_ONLY",
        backend=PIN,
        cpu_headers=headers,
        dsos=DSOS,
        providers={k: str(p) for k, p in native.items()},
        ordered_spv=P["ORDERED_SPV"],
        gpu_processes=0,
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "headers", "previous-dir", "new-output-dir"):
        p.add_argument("--" + key, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        code = inputs()
        row = build(a, out)
        row["inputs"] = code
    except Exception as e:
        row = dict(status="FAIL_PRESERVED", reason=str(e))
    save(out / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
