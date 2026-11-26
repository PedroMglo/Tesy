"""Relink the qualified SM89 library, replacing only ik's native MoE cache translation unit."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SMALL = run_path(str(HERE.parents[1] / "tiny_graph/build.py"))
need, sha, git = (SMALL[k] for k in ("need", "sha", "git"))
DSO = "5c648c09e18d29bc47d57af018053f5251f67f85bdd56cfe8f1b954c95470753"
NINJA = "1708905b01cc6a93f160620ef02b18b097c7aa2cff3f9e4e923c663c39458097"
COMMANDS = "521bcf4d7f5cc0aba254d517bdfa8963a10c1636be5970fe371b9e0054509357"
OBJECT = "src/CMakeFiles/llama.dir/llama-moe-cache.cpp.o"


def build(a, out, r):
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit and not git(HERE, "status", "--porcelain"),
        "dirty freeze",
    )
    need(
        git(a.source, "rev-parse", "HEAD") == SMALL["IK"]
        and not git(a.source, "status", "--porcelain"),
        "ik pin",
    )
    orig = a.dso.resolve()
    obj = orig / "objects"
    need(sha(orig / "receipt.json") == DSO, "qualified DSOs")
    prior = json.loads((orig / "receipt.json").read_bytes())
    need(
        all(sha(orig / k) == h for k, h in prior["libraries"].items())
        and sha(obj / "build.ninja") == NINJA
        and sha(obj / "compile_commands.json") == COMMANDS,
        "frozen objects or build plan",
    )
    src = a.source.resolve() / "src/llama-moe-cache.cpp"
    unit = next(
        c
        for c in json.loads((obj / "compile_commands.json").read_bytes())
        if c["file"].endswith("/llama-moe-cache.cpp")
    )
    from_root = str(Path(unit["file"]).parents[1])
    cc = shlex.split(unit["command"])
    cc = [v.replace(from_root, str(a.source.resolve())) if v.startswith("-I") else v for v in cc]
    need(cc[-4:] == ["-o", OBJECT, "-c", unit["file"]], "translation unit command")
    target = out / "llama-moe-cache.cpp"
    patch = HERE / "cache.patch"
    subprocess.run(
        ["patch", "--batch", "--fuzz=0", "--output", target, src, patch],
        check=True,
        capture_output=True,
        timeout=5,
    )
    candidate_obj = out / "native-cache.o"
    cc[-4:] = ["-I" + str(HERE), "-o", str(candidate_obj), "-c", str(target)]
    command = subprocess.check_output(
        ["ninja", "-C", obj, "-t", "commands", "src/libllama.so"], text=True
    ).splitlines()[-1]
    link = shlex.split(command)
    need(
        link[:2] == [":", "&&"] and link[-2:] == ["&&", ":"] and link.count(OBJECT) == 1,
        "link command",
    )
    link = link[2:-2]
    need(cc[0] == link[0] == "/usr/bin/g++-15", "C++ compiler")
    objects = {f: sha(obj / f) for f in link if f.endswith(".o")}
    need(len(objects) == 101, "original object inventory")
    r.update(
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        ik=SMALL["IK"],
        source_sha256=sha(src),
        build_parent=DSO,
        ninja_sha256=NINJA,
        commands_sha256=COMMANDS,
        compiler_sha256=sha(Path(cc[0])),
        objects=objects,
        generated_sha256=sha(target),
        inputs={
            str(p.relative_to(HERE.parents[5])): sha(p)
            for p in (
                HERE / "build.py",
                HERE / "native_input.hpp",
                patch,
                HERE.parent / "bounded_input.hpp",
                HERE.parents[1] / "bank_input.hpp",
                HERE.parents[4] / "cpu_numeric/vma/inspect.hpp",
            )
        },
        compile_argv=cc,
    )
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(out)}
    with (out / "build.log").open("xb") as log:

        def execute(argv):
            subprocess.run(
                argv, cwd=obj, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=50, check=True
            )

        def relink(name, component):
            dest = out / name / "libllama.so"
            dest.parent.mkdir()
            cmd = [
                str(component)
                if v == OBJECT
                else str(dest)
                if v == "src/libllama.so"
                else "-Wl,--dependency-file=" + str(dest.parent / "link.d")
                if v.startswith("-Wl,--dependency-file=")
                else v
                for v in link
            ]
            execute(cmd)
            return dest, cmd

        control, control_cmd = relink("control", obj / OBJECT)
        expected = prior["libraries"]["objects/src/libllama.so"]
        need(sha(control) == expected, "original objects did not reproduce qualified libllama")
        execute(cc)
        candidate, candidate_cmd = relink("candidate", candidate_obj)
        need(
            sha(candidate) != expected and sha(obj / OBJECT) == objects[OBJECT],
            "candidate/old object",
        )
        checked, third = relink("relinked", candidate_obj)
        need(sha(checked) == sha(candidate), "unstable candidate link")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    need(total < 512 << 20, "build output budget")
    inventory = hashlib.sha256(json.dumps(objects, sort_keys=True).encode()).hexdigest()
    r.update(
        status="GO_BUILD_NATIVE_CACHE_HOOK",
        control_sha256=sha(control),
        candidate_sha256=sha(candidate),
        object_inventory_sha256=inventory,
        object_sha256=sha(candidate_obj),
        bytes=total,
        link_argv=[control_cmd, candidate_cmd, third],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("source", "dso", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0, gpu_dispatches=0, http_requests=0)
    started = time.monotonic()
    try:
        build(a, out, r)
        need(time.monotonic() - started < 180, "build duration")
    except Exception as e:
        r.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    r["elapsed_s"] = time.monotonic() - started
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
