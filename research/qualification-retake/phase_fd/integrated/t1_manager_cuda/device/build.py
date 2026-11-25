"""Build the device probe without a GPU and bind its complete source and loader inputs."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
cpu = run_path(str(HERE.parent / "run.py"))
render = run_path(str(HERE / "overlay.py"))["render"]
need, digest = cpu["need"], cpu["digest"]
PROTOCOL = "80e3f74c69d0947760587b8d9d89d312b415150315b4751446a377c83ebf0b56"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source():
    need(sha(HERE / "protocol.md") == PROTOCOL, "device protocol")
    return render((HERE.parent / "consumer.cpp").read_bytes()).encode()


def providers(map_path):
    raw = map_path.read_bytes()
    need(digest(raw) == cpu["MAP_SHA"], "static provider map")
    m = json.loads(raw)
    paths = {name: Path(v[1]) for name, v in m["arms"]["C270"]["links"].items()}
    paths.update({name: Path(v) for name, v in m["driver_aliases"].items()})
    return paths, m["files"]


def verify_files(paths, files):
    for p in set(paths.values()):
        info = p.stat()
        expected = files[str(p)]
        need(
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            == tuple(expected[k] for k in ("dev", "ino", "size", "mtime_ns", "ctime_ns"))
            and sha(p) == expected["sha256"],
            f"provider identity: {p.name}",
        )


def freeze(commit):
    git = ["git", "-C", str(HERE)]
    need(
        subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() == commit
        and not subprocess.check_output([*git, "status", "--porcelain"]),
        "clean fixture commit",
    )
    return subprocess.check_output([*git, "rev-parse", "HEAD^{tree}"], text=True).strip()


def build(a, out, r):
    r.update(commit=a.commit, tree=freeze(a.commit), C269=cpu["PIN"], protocol_sha256=PROTOCOL)
    src = source()
    cp = out / "device.cpp"
    cp.write_bytes(src)
    r["source_sha256"] = digest(src)
    p, files = providers(a.map)
    verify_files(p, files)
    links = out / "libs"
    links.mkdir()
    for name, path in p.items():
        (links / name).symlink_to(path)
    table = out / "allowed.tsv"
    with table.open("x") as f:
        for path in sorted(set(p.values())):
            st = files[str(path)]
            need(not any(ch.isspace() for ch in str(path)), "provider path shape")
            print(os.major(st["dev"]), os.minor(st["dev"]), st["ino"], path, file=f)
    inc = out / "include"
    inc.mkdir()
    for h in (
        "ggml.h",
        "ggml-alloc.h",
        "ggml-backend.h",
        "ggml-cpu.h",
        "ggml-cpp.h",
        "ggml-cuda.h",
        "gguf.h",
    ):
        (inc / h).write_bytes(
            subprocess.check_output(
                ["git", "-C", a.backend, "show", f"{cpu['PIN']}:ggml/include/{h}"], timeout=10
            )
        )
    cc = Path("/usr/bin/g++-15")
    binary = out / "device"
    env = dict(
        PATH="/usr/bin:/bin", LC_ALL="C", LD_LIBRARY_PATH=str(links), CUDA_VISIBLE_DEVICES=""
    )
    r["build_s"] = cpu["elapsed"](
        [
            cc,
            "-std=c++17",
            "-O2",
            "-pthread",
            "-I",
            inc,
            cp,
            p["libggml-cuda.so.0"],
            p["libggml-cpu.so.0"],
            p["libggml-base.so.0"],
            "-Wl,-rpath-link," + str(links),
            "-ldl",
            "-o",
            binary,
        ],
        env,
        out / "build.log",
        60,
    )
    r.update(
        status="PASS_DEVICE_BUILD_ONLY",
        binary_sha256=sha(binary),
        compiler_sha256=sha(cc),
        allow_sha256=sha(table),
        map_sha256=cpu["MAP_SHA"],
        gpu_calls=0,
    )
    verify_files(p, files)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "map", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    ap.add_argument("--commit", required=True)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = {}
    try:
        build(a, out, r)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        r.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    r["wall_s"] = time.monotonic() - start
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
