"""Run the native prefix/cut fixture using the exact qualified production overlay sources."""

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
OLD = run_path(str(HERE.parent / "run.py"))
BUILD = run_path(str(HERE / "build.py"))
AUDIT = run_path(str(HERE / "audit.py"))
need, sha, save = (OLD[k] for k in ("need", "sha", "save"))


def inspect(directory, mode, native):
    journal = directory / "journal.bin"
    if mode == "off":
        need(not journal.exists(), "OFF file")
        return {"cut": 0, "enabled": False}
    with journal.open("rb") as f:
        raw = f.read(AUDIT["HEADER"].size)
    magic, version, width, capacity, tried, saved, flags, cut = AUDIT["HEADER"].unpack(raw)
    need(
        (magic, version, width, capacity) == (AUDIT["MAGIC"], 1, 96, AUDIT["CAP"])
        and tried == saved
        and journal.stat().st_size == 64 + 96 * saved,
        "fixture header",
    )
    need(cut == native["cut_before_suffix"], "prefix pointer changed after later calls")
    if mode in ("position", "retry"):
        need(flags == 5 and cut == 0, "fault was accepted")
        return {"cut": 0, "flags": flags, "enabled": True}
    need(flags == 1 and cut > 0 and saved > cut, "clean terminal cut")
    pre = list(AUDIT["iter_rows"](journal, 0, cut))
    post = list(AUDIT["iter_rows"](journal, cut, saved - cut))
    need(
        [r.call for r in pre if r.kind == 1] == list(range(1, 87))
        and pre[-1].kind == 2
        and pre[-1].call == 86
        and all(r.kind not in (13, 16, 30) for r in pre)
        and sum(r.kind == 11 for r in pre) == sum(r.kind == 17 for r in pre) == 4
        and sum(r.kind == 27 for r in pre) == 1,
        "filtered prefix",
    )
    need(
        post[0].kind == 1
        and post[0].call == 87
        and sum(r.kind == 5 for r in post) == 1440
        and sum(r.kind == 30 for r in post) == 1
        and sum(r.kind == 16 for r in post) == 3
        and sum(r.kind == 17 for r in post) == 1
        and sum(r.kind == 24 for r in post) == 4
        and post[-1].kind == 25,
        "full suffix",
    )
    before = hashlib.sha256(b"".join(AUDIT["RECORD"].pack(*r) for r in pre)).hexdigest()
    return {"cut": cut, "prefix_sha256": before, "records": saved, "enabled": True}


def run(a, out, r):
    lib = run_path(str(OLD["PARENT"]))

    def git(*args):
        return lib["git"](HERE, *args).decode().strip()

    need(git("rev-parse", "HEAD") == a.commit and not git("status", "--porcelain"), "clean freeze")
    observe = lib["cgroup_reader"](OLD["QUAL"].parents[1], a.scope_unit)
    r.update(
        scope_before=observe(),
        commit=a.commit,
        model_launches=0,
        build_receipt_sha256=a.build_sha256,
    )
    need(sha(a.build_dir / "receipt.json") == a.build_sha256, "DSO authority")
    build = json.loads((a.build_dir / "receipt.json").read_bytes())
    need(
        build["status"] == "PASS_C291_FULL_PREFIX_DSO_STATIC_C281"
        and build["profile_header_sha256"] == BUILD["HEADER"]
        and build["profile_patch_sha256"] == sha(HERE / "profile.patch"),
        "production overlay",
    )
    private = out / "private"
    blobs = lib["extract"](a.backend, private)
    r["input_blobs"] = lib["canonical"](blobs)
    for name, digest in build["overlay_sha256"].items():
        src = a.build_dir / "overlay/src" / name
        need(sha(src) == digest, f"DSO source {name}")
        shutil.copyfile(src, private / "src" / name)
    code = (private / "src/llama-context.cpp").read_text()
    inc = run_path(str(OLD["PFJ"] / "native_fixture.py"))["borrowed"](code)
    (private / "src/borrowed-context.inc").write_text(inc)
    need(
        sha(HERE.parent / "fixture.cpp")
        == "23fbc0515e42af296f3b2db92eeb09d15371e374f5e046c6809f5a0bdfe318cc",
        "base fixture",
    )
    shutil.copyfile(HERE.parent / "fixture.cpp", private / "fixture.cpp")
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(a.libs),
    }

    def invoke(cmd, cwd, name, procenv):
        with (
            (cwd / (name + ".stdout")).open("xb") as so,
            (cwd / (name + ".stderr")).open("xb") as se,
        ):
            subprocess.run(cmd, cwd=cwd, env=procenv, check=True, stdout=so, stderr=se, timeout=150)

    invoke(
        ["/usr/bin/patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", HERE / "fixture.patch"],
        private,
        "fixture",
        env,
    )
    cc = Path("/usr/bin/g++").resolve()
    libs = {k: (a.libs / f"libggml-{k}.so.0.15.3").resolve() for k in OLD["LIBS"]}
    need(
        sha(cc) == "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"
        and {k: sha(v) for k, v in libs.items()} == OLD["LIBS"],
        "compiler/ggml providers",
    )
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
            *["-I" + str(private / s) for s in ("src", "include", "ggml/include")],
            private / "fixture.cpp",
            *[private / "src" / s for s in lib["BUILD_INPUTS"]],
            "-Wl,--gc-sections",
            "-Wl,--wrap=pread",
            libs["cpu"],
            libs["base"],
            "-o",
            child,
        ],
        out,
        "compile",
        env,
    )
    invoke(["/usr/bin/ldd", child], out, "ldd", env)
    aliases = {
        line.split()[0]: line.split()[2]
        for line in (out / "ldd.stdout").read_text().splitlines()
        if " => " in line
    }
    need(
        set(aliases)
        == {
            "libggml-cpu.so.0",
            "libggml-base.so.0",
            "libstdc++.so.6",
            "libgcc_s.so.1",
            "libc.so.6",
            "libm.so.6",
            "libgomp.so.1",
        }
        and all(Path(aliases[f"libggml-{k}.so.0"]).resolve() == v for k, v in libs.items()),
        "loader",
    )
    r["binary_sha256"] = sha(child)
    r["data"] = OLD["materialize"](a.new_data_dir)
    r["cases"] = {}
    slots = None
    for mode in ("off", "on", "position", "retry"):
        directory = out / mode
        directory.mkdir()
        extra = {} if mode == "off" else {"TESY_PHASE_FD_FILE": str(directory / "journal.bin")}
        if mode in ("position", "retry"):
            extra["TESY_FIX_CUT_FAULT"] = mode
        invoke(
            [child, "pack", a.new_data_dir, directory / "native.json"],
            directory,
            "process",
            env | extra,
        )
        native = json.loads((directory / "native.json").read_bytes())
        need(
            native["joined_workers"] == 4 and native["status"] == "PASS_PACK_NATIVE_CASE", "native"
        )
        if mode in ("off", "on"):
            need(
                native["store_loads"] == 5
                and native["validated_matrix_bytes"] == 5 * 3 * 4_406_400,
                "real slots/payload",
            )
            need(slots is None or slots == native["native_slots"], "OFF/ON slots")
            slots = native["native_slots"]
        result = inspect(directory, mode, native)
        r["cases"][mode] = result | {
            "files": {f.name: sha(f) for f in directory.iterdir() if f.is_file()}
        }
    r.update(
        header_sha256=build["profile_header_sha256"],
        profile_patch_sha256=build["profile_patch_sha256"],
        scope_after=observe(),
        status="PASS_FULL_PREFIX_NATIVE_CUT",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "libs", "build-dir", "new-output-dir", "new-data-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    for k in ("scope-unit", "commit", "build-sha256"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    start = time.monotonic()
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        run(a, a.new_output_dir, r)
    except Exception as exc:
        r.update(reason=f"{type(exc).__name__}: {exc}")
    r["elapsed_s"] = time.monotonic() - start
    save(a.new_output_dir / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
