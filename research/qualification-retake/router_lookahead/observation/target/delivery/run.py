"""One model-free family on the C305 worker using the C291 packed FD and real GGML CPU SET."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[3]
ROOT = QUAL.parents[1]
P = run_path(str(QUAL / "packed_worker/run.py"))
need, sha, git = (P[k] for k in ("need", "sha", "git"))
PIN = "c94780b12820c7b3fb20f2a9acf38bb27506c6ae"
TREE = "e418713c063a33214d5bf75f3ff25b40090ab7a1"
C291 = P["PIN"]
OBSERVER = "7abb8c47c87044220482c31f8baebbf57796005f61295fb3e4fe3d131e848d08"
COMPILER = "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"


def extract(backend, destination):
    git(backend, "merge-base", "--is-ancestor", C291, PIN)
    need(git(backend, "rev-parse", PIN + "^{tree}").decode().strip() == TREE, "C305 source tree")
    entries = git(
        backend,
        "ls-tree",
        "-r",
        "-z",
        PIN,
        "ggml/include",
        "include",
        "vendor/nlohmann",
        *P["CORE"],
        "src/c305-cpu-stage.h",
        "src/c294-service-window.h",
    ).split(b"\0")[:-1]
    need(len(entries) == 36, "C305 manager sources")
    paths = {}
    destination.mkdir()
    for item in entries:
        left, rel = item.decode().split("\t")
        flags, oid = left.rsplit(" ", 1)
        need(flags == "100644 blob", "unexpected object")
        target = destination / rel
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(git(backend, "cat-file", "blob", oid))
        need(git(backend, "hash-object", str(target)).decode().strip() == oid, "source bytes")
        paths[rel] = oid
    return paths


def write_pack(p):
    with p.open("xb") as f:
        for e in range(5):
            for k in range(3):
                f.write(bytes((1 + 13 * e + 29 * k + i % 113) % 256 for i in range(4096)))
            f.write(bytes([222]) * 4096)
    p.chmod(0o400)


def run(a, out, r):
    need(
        git(ROOT, "rev-parse", "HEAD").decode().strip() == a.commit
        and not git(ROOT, "status", "--porcelain"),
        "clean frozen checkout",
    )
    need(sha(Path("/usr/bin/c++")) == COMPILER, "pinned compiler")
    gate = P["cgroup_reader"](ROOT, a.unit)
    r["initial_scope"] = gate()
    libs_expected = {
        "base": P["LIBS"]["ggml"],
        "cpu": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    }
    need(sha(a.observation / "receipt.json") == OBSERVER, "qualified producer fixture")
    libs = [a.libs / f"libggml-{s}.so.0.15.3" for s in ("cpu", "base")]
    need(
        all(sha(p) == libs_expected[s] for p, s in zip(libs, ("cpu", "base"), strict=True)),
        "qualified GGML CPU/base libraries",
    )
    src = out / "private"
    inputs = extract(a.backend, src)
    run_path(str(HERE / "overlay.py"))["apply"](src / "src")
    r.update(
        commit=a.commit,
        tree=git(ROOT, "rev-parse", "HEAD^{tree}").decode().strip(),
        pins=[C291, PIN],
        inputs=P["canonical"](inputs),
        compiler_sha256=COMPILER,
        native_sources={p.name: sha(p) for p in (src / "src").iterdir()},
        protocol_sha256=sha(HERE / "protocol.md"),
    )
    pack = out / "marker.pack"
    write_pack(pack)
    fstype = subprocess.check_output(
        ["findmnt", "-no", "FSTYPE,SOURCE", "-T", out], text=True
    ).strip()
    need(fstype.startswith("btrfs") and "nvme" in fstype, "private internal Btrfs marker")
    exe = out / "fixture"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": str(a.libs),
    }

    def command(argv, label):
        with (
            (out / (label + ".stdout")).open("xb") as stdout,
            (out / (label + ".stderr")).open("xb") as stderr,
        ):
            proc = subprocess.run(argv, cwd=out, env=env, stdout=stdout, stderr=stderr, timeout=120)
        need(proc.returncode == 0, f"{label} exited {proc.returncode}")
        gate()

    command(
        [
            "/usr/bin/c++",
            "-std=c++17",
            "-pthread",
            "-O0",
            "-g0",
            "-fPIC",
            "-pie",
            "-DTESY_C305_STAGE_TESTING",
            "-DTESY_STORE_TESTING",
            "-ffunction-sections",
            "-fdata-sections",
            *["-I" + str(src / d) for d in ("src", "include", "ggml/include")],
            str(HERE / "fixture.cpp"),
            *[str(src / "src" / name) for name in P["BUILD_INPUTS"]],
            "-Wl,--gc-sections",
            "-Wl,--wrap=pread",
            "-Wl,--wrap=ggml_backend_tensor_set",
            *map(str, libs),
            "-o",
            exe,
        ],
        "build",
    )
    command(["/usr/bin/ldd", exe], "loader")
    mapped = {}
    for row in (out / "loader.stdout").read_text().splitlines():
        if "=>" not in row:
            continue
        name, loc = row.split("=>")
        mapped[name.strip()] = Path(loc.strip().split()[0])
    need(
        not any(
            any(s in n.lower() for s in ("cuda", "cublas", "nvidia", "libllama")) for n in mapped
        )
        and all(
            sha(mapped["libggml-" + s + ".so.0"]) == sha(p)
            for s, p in zip(("cpu", "base"), libs, strict=True)
        ),
        "CPU-only loaded providers",
    )
    r.update(pack_sha256=sha(pack), pack_bytes=pack.stat().st_size, binary_sha256=sha(exe), arms={})
    for mode in ("OFF", "ON", "STALE"):
        command([exe, pack, mode], mode)
        row = json.loads((out / (mode + ".stdout")).read_bytes())
        need(
            row["mode"] == mode and row["manager_destroyed"] and row["workers"] == 4,
            "workers and cleanup",
        )
        r["arms"][mode] = row
    off, on, stale = (r["arms"][m] for m in ("OFF", "ON", "STALE"))
    need(
        off["primary"] == on["primary"]
        and off["initial"] == on["initial"]
        and off["routed_slots"] == on["routed_slots"]
        and off["proposal"] == on["proposal"]
        and stale["status"] == "PASS_STALE_OWNER_REJECTED",
        "paired ownership/slots or fault",
    )
    need(sha(pack) == r["pack_sha256"], "marker modified")
    r["final_scope"] = gate()
    r["status"] = "PASS_PREFILL_PACKED_DELIVERY_FIXTURE"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "observation", "libs", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    for k in ("unit", "commit"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    begin = time.monotonic()
    r = dict(status="FAIL_PRESERVED", model_forwards=0)
    try:
        run(a, a.new_output_dir, r)
    except Exception as e:
        r["error"] = repr(e)
    r["elapsed_s"] = time.monotonic() - begin
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2)
        f.write("\n")
    print(r["status"], r.get("error", ""))
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
