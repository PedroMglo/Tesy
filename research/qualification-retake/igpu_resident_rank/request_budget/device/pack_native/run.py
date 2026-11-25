"""Build the PFJ overlay privately and exercise one true C291 CPU worker pool per case."""

import argparse
import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[3]
PFJ = QUAL / "phase_fd/integrated"
PARENT = QUAL / "packed_worker/run.py"
PIN = "c89c88b342054223e3f27a17fbfd0954803147ac"
METHOD = "9d69588b84947be5aa7b0b5ffd2ca88427dc3c9c449c631ea6b78aca27149e84"
S = 4406400
W = 13221888
D = 13258752
G = 36 << 20
CASES = ("pack-off", "pack-on", "gguf-off", "gguf-on", "pack-short-on")
LIBS = {
    "cpu": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "base": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")


def materialize(data):
    data.mkdir()
    pack = data / "pack.test"
    gguf = data / "gguf.test"
    for f, size, form in ((pack, 6 * D, "pack"), (gguf, 3 * G, "gguf")):
        with f.open("xb") as stream:
            stream.truncate(size)
            for e in range(6):
                for k in range(3):
                    offset = e * D + k * S if form == "pack" else k * G + e * S
                    tag = 16 * e + k + 1
                    stream.seek(offset)
                    stream.write(bytes((tag,)))
                    stream.seek(offset + S - 1)
                    stream.write(bytes((tag + 80,)))
        f.chmod(0o400)
    return {f.name: dict(size=f.stat().st_size, blocks512=f.stat().st_blocks) for f in (pack, gguf)}


def run(a, out, r):
    need(
        sha(HERE / "protocol.md") == METHOD
        and sha(PARENT) == "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e",
        "frozen sources",
    )
    need(
        sha(PFJ / "native_fixture.py")
        == "8b9dfdbef77c3c882cf4a759cf90a7d4c7ad517cb9a946abe8a54e3fb7f61e23"
        and sha(PFJ / "phase-fd-integrated.h")
        == "350be0c2ad384c2acbbb06c62eeb9258d011e0c94f8a3d535b2ca82c3ba376a8",
        "PFJ",
    )
    lib = run_path(PARENT)
    rev = lib["git"](HERE, "rev-parse", "HEAD").decode().strip()
    need(rev == a.commit and not lib["git"](HERE, "status", "--porcelain"), "frozen clean checkout")
    observe = lib["cgroup_reader"](QUAL.parents[1], a.scope_unit)
    r.update(
        commit=rev,
        tree=lib["git"](HERE, "rev-parse", "HEAD^{tree}").decode().strip(),
        scope_before=observe(),
        protocol_sha256=METHOD,
        sources={
            n: sha(HERE / n) for n in ("observer.patch", "fixture.cpp", "run.py", "protocol.md")
        },
    )
    private = out / "private"
    sources = lib["extract"](a.backend, private)
    context = lib["git"](a.backend, "show", PIN + ":src/llama-context.cpp")
    info = b"blob " + str(len(context)).encode() + b"\0" + context
    need(
        hashlib.sha1(info).hexdigest() == "8fa5850bc96afba2a1d01d11d1344bd94fcc531e",
        "exact C291 context",
    )
    (private / "src/llama-context.cpp").write_bytes(context)
    shutil.copyfile(PFJ / "phase-fd-integrated.h", private / "src/phase-fd-integrated.h")

    def invoke(cmd, name, env, cwd=out, output=None):
        raw = output or out
        with (
            (raw / (name + ".stdout")).open("xb") as log,
            (raw / (name + ".stderr")).open("xb") as err,
        ):
            subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=err, timeout=240, check=True)

    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(a.libs),
    }
    libs = {k: (a.libs / ("libggml-" + k + ".so.0.15.3")).resolve(strict=True) for k in LIBS}
    need(all(sha(libs[k]) == v for k, v in LIBS.items()), "CPU/base providers")
    invoke(
        ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", HERE / "observer.patch"],
        "apply",
        env,
        private,
    )
    new = (private / "src/llama-context.cpp").read_text()
    (private / "src/borrowed-context.inc").write_text(
        run_path(PFJ / "native_fixture.py")["borrowed"](new)
    )
    cc = Path("/usr/bin/g++").resolve(strict=True)
    need(sha(cc) == "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63", "compiler")
    child = out / "worker"
    invoke(
        [
            cc,
            "-std=c++17",
            "-DTESY_STORE_TESTING",
            "-pthread",
            "-O0",
            "-g0",
            "-Wall",
            "-Wextra",
            "-fPIC",
            "-pie",
            "-fno-plt",
            "-ffunction-sections",
            "-fdata-sections",
            *["-I" + str(private / x) for x in ("src", "include", "ggml/include")],
            HERE / "fixture.cpp",
            *[private / "src" / x for x in lib["BUILD_INPUTS"]],
            "-Wl,--gc-sections",
            "-Wl,--wrap=pread",
            libs["cpu"],
            libs["base"],
            "-o",
            child,
        ],
        "compile",
        env,
    )
    invoke(["/usr/bin/ldd", child], "loader", env)
    loaded = (out / "loader.stdout").read_text()
    for _, lib_path in libs.items():
        name = lib_path.name.split(".so.")[0] + ".so.0"
        lines = [row for row in loaded.splitlines() if row.strip().startswith(name + " => ")]
        need(
            len(lines) == 1 and Path(lines[0].split()[2]).resolve() == lib_path,
            "actual DSO " + name,
        )
    need(all(x not in loaded for x in ("cuda", "vulkan", "nvidia", "not found")), "CPU only")
    r.update(
        backend=PIN,
        backend_tree=lib["TREE"],
        input_blobs=lib["canonical"](sources),
        binary_sha256=sha(child),
        libs=LIBS,
        overlay={
            p.name: sha(p)
            for p in (private / "src").iterdir()
            if p.name
            in (
                "llama-context.cpp",
                "llama-moe-stream.cpp",
                "phase-fd-integrated.h",
                "borrowed-context.inc",
            )
        },
    )
    r["archives"] = materialize(a.new_data_dir)
    r["cases"] = {}
    for case in CASES:
        place = out / case
        place.mkdir()
        child_env = dict(env)
        if case.endswith("-on"):
            child_env["TESY_PHASE_FD_FILE"] = str(place / "journal.bin")
        mode = "short" if case == "pack-short-on" else case.split("-")[0]
        invoke(
            [child, mode, a.new_data_dir, place / "native.json"], "process", child_env, output=place
        )
        native = json.loads((place / "native.json").read_text())
        need(
            native["status"] == "PASS_PACK_NATIVE_CASE" and native["joined_workers"] == 4,
            "native result",
        )
        need((place / "journal.bin").exists() == case.endswith("-on"), "opt-in")
        r["cases"][case] = {f.name: sha(f) for f in sorted(place.iterdir()) if f.is_file()}
    r["scope_after"] = observe()
    r["status"] = "PASS_PACK_NATIVE_FIXTURE_EXECUTIONS"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "libs", "new-output-dir", "new-data-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("scope-unit", "commit"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    tic = time.monotonic()
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        run(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    r["elapsed_s"] = time.monotonic() - tic
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
