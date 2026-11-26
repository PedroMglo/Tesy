"""Link the warm page-copy client against the externally sealed SM89 build."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE.parent / "client/build.py"))
CONFIG = run_path(str(HERE.parent / "configure.py"))
need, pin, sha = BASE["need"], BASE["pin"], BASE["sha"]
COMPACT = "749c0849a9ce3112bed8a41c36b125e33435e6a72e5f9852fed62a23fe8d20e8"
GEOMETRY = HERE.parents[1] / "result.json"


def sources():
    return {
        p: sha(HERE / p)
        for p in (
            "protocol.md",
            "transfer.cpp",
            "build.py",
            "grade.py",
            "run.py",
            "../client/copy.cpp",
            "../client/hooks.hpp",
            "../client/build.py",
            "../device/run.py",
        )
    }


def build(a):
    head = subprocess.check_output(["git", "-C", HERE, "rev-parse", "HEAD"], text=True).strip()
    need(
        head == a.commit
        and not subprocess.check_output(["git", "-C", HERE, "status", "--porcelain"]),
        "dirty or unsealed checkout",
    )
    dso = json.loads(pin(a.dso / "receipt.json", a.dso_sha256).read_bytes())
    need(dso["status"] == "PASS_IK_SM89_LINK_ONLY", "unqualified SM89 build")
    CONFIG["pin"](a.source)
    pin(GEOMETRY, COMPACT)
    obj = (a.dso / "objects").resolve()
    libs = [pin(obj / n, dso["libraries"]["objects/" + n]) for n in BASE["LIBS"]]
    config = CONFIG["providers"](a.env49_map)
    toolkit = CONFIG["TOOLKIT"]
    env49 = json.loads(a.env49_map.read_bytes())
    binary = a.new_output_dir / "warm-transfer"
    compiler = Path("/usr/bin/g++-15")
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O2",
        "-rdynamic",
        "-fPIC",
        "-pie",
        "-fno-plt",
        "-pthread",
        *["-I" + str(a.source / p) for p in ("ggml/include", "vendor")],
        "-I" + str(toolkit / "include"),
        str(HERE / "transfer.cpp"),
        str(HERE.parent / "client/copy.cpp"),
        "-Wl,--no-as-needed",
        *map(str, libs),
        "-ldl",
        *[
            "-Wl,-rpath-link," + str(p)
            for p in (obj / "ggml/src", Path(env49["driver_dir"]), toolkit / "lib64")
        ],
        "-o",
        str(binary),
    ]
    with (a.new_output_dir / "compile.log").open("xb") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    paths, closure = BASE["device_closure"](binary, obj, dso, a)
    imports = BASE["imported"](libs[1])
    need({"cudaMemcpyAsync", "cudaHostRegister"} <= set(imports), "missing copy/register imports")
    return dict(
        status="PASS_HOT_TRANSFER_BUILD",
        committed_source=head,
        binary_sha256=sha(binary),
        compiler_sha256=sha(compiler.resolve()),
        dso_sha256=a.dso_sha256,
        geometry_sha256=COMPACT,
        cuda_runtime_headers_sha256=sha(toolkit / "include/cuda_runtime_api.h"),
        source_sha256=sources(),
        ik_commit=BASE["FRONT"]["PIN"],
        providers=config,
        loader=closure,
        search=paths,
        cuda_imports=imports,
        command=cmd,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("dso", "source", "env49-map", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--dso-sha256", required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = build(a)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=str(exc))
    CONFIG["write"](a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
