"""Build and reopen the normal versus dry-run CPU loader on the sealed two-layer GPT-OSS."""

import argparse
import json
import os
import resource
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IK = HERE.parents[1]
TINY = run_path(str(IK / "tiny_loader/run.py"))
FRONT = TINY["FRONT"]
WEIGHTS = run_path(str(HERE.parent / "client/grade.py"))["WEIGHTS"]
need, sha = TINY["need"], TINY["sha"]
GGUF = "3771d5de5067095852a0132324c16b01e39c2b999082d4a3b6165e13aff90644"


def limits():
    for kind, n in (
        (resource.RLIMIT_AS, 768 << 20),
        (resource.RLIMIT_FSIZE, 16 << 20),
        (resource.RLIMIT_CORE, 0),
    ):
        resource.setrlimit(kind, (n, n))


def run(a, out, r):
    src, obj = a.source.resolve(), a.objects.resolve()
    head, tree = subprocess.check_output(
        ["git", "-C", src, "rev-parse", "HEAD", "HEAD^{tree}"], text=True
    ).split()
    need(
        (head, tree) == (FRONT["PIN"], FRONT["TREE"])
        and not subprocess.check_output(["git", "-C", src, "status", "--porcelain"]),
        "ik source",
    )
    need(sha(a.tiny) == GGUF and a.tiny.stat().st_size == 3390592, "tiny only")
    for name, digest in TINY["BASE"].items():
        need(sha(obj / name) == digest, "CPU DSO")
    tool = out / "probe"
    command = [
        "/usr/bin/g++-15",
        "-std=c++17",
        "-O1",
        "-pthread",
        *(f"-I{src / p}" for p in ("include", "ggml/include")),
        str(HERE / "probe.cpp"),
        *(str(obj / k) for k in TINY["BASE"]),
        "-Wl,-rpath-link," + str(obj / "ggml/src"),
        "-o",
        str(tool),
    ]
    with (out / "compile.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=20, check=True)
    closure = FRONT["closure"](tool, obj)
    r.update(
        ik_commit=head,
        ik_tree=tree,
        compiler_sha256=sha(Path(command[0]).resolve()),
        source_sha256=sha(HERE / "probe.cpp"),
        runner_sha256=sha(HERE / "run.py"),
        protocol_sha256=sha(HERE / "protocol.md"),
        vma_sha256=sha(IK / "cpu_numeric/vma/inspect.hpp"),
        fixture_sha256=GGUF,
        closure=closure,
        binary_sha256=sha(tool),
        arms={},
        contexts=0,
        forwards=0,
    )
    # Mount only CPU providers, the executable, the fixture and system libraries.
    box = [
        "/usr/bin/bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--ro-bind",
        "/usr/lib64",
        "/lib64",
        "--dir",
        "/providers",
    ]
    for name, info in closure.items():
        if name in {"libggml.so", "libllama.so"}:
            box.extend(["--ro-bind", info["file"], "/providers/" + name])
    box.extend(
        [
            "--ro-bind",
            str(tool),
            "/probe",
            "--ro-bind",
            str(a.tiny.resolve()),
            "/fixture.gguf",
            "--",
        ]
    )
    expected = {f"blk.{i}.ffn_{role}_exps.weight": off for (i, role), off in WEIGHTS.items()}
    for mode in ("NORMAL", "DRY"):
        log = out / (mode + ".log")
        with log.open("xb") as f:
            proc = subprocess.run(
                [*box, "/probe", mode, "/fixture.gguf"],
                stdin=subprocess.DEVNULL,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=dict(
                    LC_ALL="C",
                    LD_LIBRARY_PATH="/providers:/lib64",
                    OMP_NUM_THREADS="1",
                    OPENBLAS_NUM_THREADS="1",
                    GGML_CUDA_NO_PINNED="1",
                ),
                timeout=20,
                preexec_fn=limits,
            )
        need(proc.returncode == 0, f"{mode} child {proc.returncode}")
        vals = {}
        for line in log.read_text().splitlines():
            if line.startswith("VIEW "):
                _, name, *fields = line.split()
                need(name in expected and name not in vals and len(fields) == 5, "tensor census")
                vals[name] = [int(v) for v in fields]
        need(vals.keys() == expected.keys(), "missing tensor")
        bound = sum(row == [1, 1, 1, 1, expected[n]] for n, row in vals.items())
        r["arms"][mode] = dict(bound=bound, tensors=vals)
        if mode == "NORMAL":
            need(bound == 6, "normal control not mapped")
    r["status"] = (
        "GO_CHECK_DEVICE_BINDING"
        if r["arms"]["DRY"]["bound"] == 6
        else "NO_GO_DRY_RUN_FOR_BANK_CAPACITY"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("source", "objects", "tiny", "new-output"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output.resolve()
    out.mkdir(mode=0o700)
    r = {"status": "FAIL_PRESERVED"}
    try:
        run(a, out, r)
    except Exception as exc:
        r["reason"] = str(exc)
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
