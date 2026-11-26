"""Produce the CUDA consumer and true C291 manager without using a CUDA device."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[2] / "t1_manager_cuda/device"
pre = run_path(str(PRIOR / "build.py"))
packed = run_path(str(HERE.parents[4] / "packed_worker/run.py"))
source = run_path(str(HERE / "overlay.py"))["render"]
sha, need, verify_files = (pre[k] for k in ("sha", "need", "verify_files"))
PROTOCOL = "b15808682ebc4cbe36b9f339d31401e2b4d4f4bf46a14a28a9b8f64ea240942f"


def providers(map_path):
    paths, files = pre["providers"](map_path)
    for name in ("libcrypto.so.3", "libz.so.1"):
        path = (Path("/usr/lib64") / name).resolve(strict=True)
        need(str(path) in files, "additional ELF missing from signed C269 map")
        paths[name] = path
    need(files[str(paths["libcrypto.so.3"])]["sha256"] == packed["LIBS"]["crypto"], "same OpenSSL")
    return paths, files


def build(a, out, r):
    need(sha(HERE / "protocol.md") == PROTOCOL, "prospective protocol")
    r.update(
        commit=a.commit,
        tree=pre["freeze"](a.commit),
        C291=packed["PIN"],
        C291_tree=packed["TREE"],
        C269=pre["cpu"]["PIN"],
        protocol_sha256=PROTOCOL,
        gpu_calls=0,
    )
    private = out / "private-c291"
    original = packed["extract"](a.backend.resolve(), private)
    r["private_sources_sha256"] = packed["canonical"](original)
    seam = run_path(str(HERE.parent / "overlay.py"))
    seam["patch_private"](private)
    r["worker_sha256"] = sha(private / "src/llama-moe-stream.cpp")
    cp = out / "device.cpp"
    cp.write_bytes(source())
    r["source_sha256"] = sha(cp)
    paths, files = providers(a.map)
    verify_files(paths, files)
    links = out / "libs"
    links.mkdir()
    for name, p in paths.items():
        (links / name).symlink_to(p)
    table = out / "allowed.tsv"
    pre["write_vma_table"](table, paths, files)
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(links),
        "CUDA_VISIBLE_DEVICES": "",
    }
    cc = Path("/usr/bin/g++-15")
    exe = out / "device"
    argv = [
        cc,
        "-std=c++17",
        "-O1",
        "-g0",
        "-pthread",
        "-DTESY_STORE_TESTING",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
    ]
    argv += ["-I" + str(private / folder) for folder in ("src", "include", "ggml/include")]
    argv += [
        cp,
        *(private / "src" / f for f in packed["BUILD_INPUTS"]),
        "-Wl,--gc-sections",
        "-Wl,--wrap=pread",
        "-Wl,--wrap=ggml_backend_tensor_set",
        paths["libggml-cuda.so.0"],
        paths["libggml-cpu.so.0"],
        paths["libggml-base.so.0"],
        paths["libcrypto.so.3"],
        "-Wl,-rpath-link," + str(links),
        "-ldl",
        "-o",
        exe,
    ]
    r["build_s"] = pre["cpu"]["elapsed"](argv, env, out / "build.log", 120)
    r["startup_objects"] = pre["inspect_loader"](
        paths["ld-linux-x86-64.so.2"], links, exe, paths, out
    )
    passive = out / "passive"
    pre["cpu"]["elapsed"](
        [cc, "-std=c++17", "-O2", PRIOR / "passive.cpp", "-o", passive],
        env,
        out / "passive-build.log",
        30,
    )
    pre["cpu"]["elapsed"](
        [passive, out], env | {"TESY_FIXTURE_MAP": str(table)}, out / "passive.log", 10
    )
    need(
        set((out / "passive.providers").read_text().splitlines()) == set(map(str, paths.values())),
        "passive VMA guard",
    )
    verify_files(paths, files)
    r.update(
        status="PASS_TILE_CUDA_BUILD_ONLY",
        binary_sha256=sha(exe),
        allow_sha256=sha(table),
        map_sha256=pre["cpu"]["MAP_SHA"],
        loader_sha256=sha(out / "loader.json"),
        compiler_sha256=sha(cc),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "map", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    begin = time.monotonic()
    r = {"status": "FAIL_PRESERVED"}
    try:
        build(args, out, r)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        r["reason"] = str(e)
    r["wall_s"] = time.monotonic() - begin
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
