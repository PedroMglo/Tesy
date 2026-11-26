"""Detached, private replay of the pinned ik frontend against C281 parts."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parents[1] / "history_lookup/native_ids/verify.py"
PIN = "7a5d90009b7ae55d3239cdd33244977c4eb10ff6"
TREE = "a1706c85dc11d32b0fc34e20d699066a88b56201"
ARCHIVE = "6813a262354cb3eaa518aac1cfb777749b0812c8c548e7665d6f3748f91f94e9"
FIXED = "0ccef2b31697ba30f891ed18cfc1203b8603f26fc4233faa98839c674819b9eb"
VOCAB = "ac4566b560fe2df4e0f4f9eb071ce8803af7107c022b4a643a842560ba8b7049"
CAPTURE = "tesy-natural-ids-capture-20261125-r01"
VERIFIED = "tesy-natural-ids-verified-20261125-r01"
LOADER = Path("/lib64/ld-linux-x86-64.so.2")
FILES = ("common/libcommon.a", "src/libllama.so", "ggml/src/libggml.so")


def need(ok, label):
    if not ok:
        raise ValueError(label)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pinned(path, expected):
    need(path.is_file() and sha(path) == expected, "artifact SHA " + path.name)
    return path


def inputs(part):
    manifest = json.loads(pinned(part / "manifest.json", ARCHIVE).read_bytes())["files"]

    def archived(name):
        path = part / name
        desc = manifest[name]
        need(not path.is_symlink() and path.stat().st_size == desc["bytes"], "archive member")
        return pinned(path, desc["sha256"])

    spec = importlib.util.spec_from_file_location("c281_verified_inputs", REFERENCE)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    printed = json.loads(archived(f"{VERIFIED}/receipt.json").read_bytes())
    need(printed["status"] == "PASS_TWO_NATURAL_SAMPLED_TRAJECTORIES", "C281 gate")
    archived(f"{CAPTURE}/receipt.json")
    turns = []
    for i, geom in enumerate(reference.GEOMETRY, 1):
        label = f"T{i}"
        for name in ("input.json", "request.jsonl", "result.json"):
            archived(f"{CAPTURE}/raw/{label}-{name}")
        inp, message, frames, _ = reference.projection(part / CAPTURE / "raw", i, geom)
        need(
            inp["template_kwargs"]
            == {"tesy_template_date": "2026-10-05", "reasoning_effort": "medium"},
            "request kwargs",
        )
        p = archived(f"{VERIFIED}/{label}-sampled.i32")
        rec = printed["turns"][i - 1]
        need(
            (rec["label"], rec["count"], p.stat().st_size, sha(p))
            == (label, geom[2], 4 * geom[2], rec["sampled_ids_sha256"]),
            "sample vector",
        )
        deltas = []
        for frame in frames:
            for choice in frame["choices"]:
                delta = {
                    k: v
                    for k, v in choice["delta"].items()
                    if k in ("reasoning_content", "content") and v
                }
                if delta:
                    deltas.append(delta)
        turns.append(
            dict(
                messages=inp["messages"],
                rendered_prompt=inp["rendered_prompt"],
                official_ids=inp["official_ids"],
                sampled=struct.unpack(f"<{geom[2]}i", p.read_bytes()),
                message=message,
                deltas=deltas,
            )
        )
    a, b = turns
    need(b["official_ids"][:2043] == a["official_ids"], "inter-turn input prefix")
    need(
        b["messages"][:-2] == a["messages"]
        and b["messages"][-2] == {"role": "assistant", "content": a["message"]["content"]},
        "natural assistant turn",
    )
    return turns


def env(objects):
    return {
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "LD_LIBRARY_PATH": os.pathsep.join(str(objects / p) for p in ("src", "ggml/src")),
    }


def closure(exe, objects):
    result = subprocess.check_output([LOADER, "--list", exe], env=env(objects), text=True)
    providers = {
        name: Path(path).resolve()
        for name, path in re.findall(r"^\s*(\S+)\s+=>\s+(/\S+)\s+\(", result, flags=re.M)
    }
    for target in FILES[1:]:
        p = (objects / target).resolve()
        need(providers.get(Path(target).name) == p, "loader provider " + str(p.name))
    need(not re.search(r"lib(?:cuda|vulkan|hip|cublas)", result, flags=re.I), "non-CPU provider")
    relocated = subprocess.run(
        ["/usr/bin/ldd", "-r", exe], env=env(objects), capture_output=True, text=True, timeout=15
    )
    need(
        relocated.returncode == 0
        and not re.search("undefined symbol|not found", relocated.stdout + relocated.stderr),
        "unresolved runtime symbols",
    )
    providers[LOADER.name] = LOADER.resolve()
    return {k: {"file": str(v), "sha256": sha(v)} for k, v in sorted(providers.items())}


def build(a, out, result):
    src, obj = a.src.resolve(), a.objects.resolve()

    def git(*args):
        return subprocess.check_output(["git", "-C", src, *args], text=True).strip()

    need(
        git("rev-parse", "HEAD") == PIN
        and git("rev-parse", "HEAD^{tree}") == TREE
        and not git("status", "--porcelain", "--untracked-files=no"),
        "ik source",
    )
    cache = (obj / "CMakeCache.txt").read_text()
    for s in (
        "GGML_CUDA:BOOL=OFF",
        "GGML_VULKAN:BOOL=OFF",
        "LLAMA_CURL:BOOL=OFF",
        f"CMAKE_HOME_DIRECTORY:INTERNAL={src}",
    ):
        need(s in cache.splitlines(), "CPU build configuration")
    libs = {s: sha(obj / s) for s in FILES}
    exe = out / "probe"
    cmd = ["/usr/bin/c++", "-std=c++17", "-O1", "-pthread"]
    cmd += [
        f"-I{src / folder}" for folder in ("common", "include", "ggml/include", "vendor", "src")
    ]
    cmd += [
        str(HERE / "probe.cpp"),
        str(obj / FILES[0]),
        str(obj / FILES[1]),
        str(obj / FILES[2]),
        "-ldl",
        "-o",
        str(exe),
    ]
    with (out / "compile.log").open("xb") as log:
        run = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=180, env=env(obj))
    need(run.returncode == 0, "compile failure")
    result.update(
        ik_commit=PIN,
        ik_tree=TREE,
        objects=str(obj),
        libraries=libs,
        compile_argv=cmd,
        compiler_sha256=sha(Path(cmd[0]).resolve()),
        binary_sha256=sha(exe),
        closure=closure(exe, obj),
        status="PASS_IK_FRONTEND_BUILD",
    )


def resource_limits():
    resource.setrlimit(resource.RLIMIT_AS, (2**30, 2**30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def verify(a, out, result):
    b = json.loads(pinned(a.build / "receipt.json", a.build_sha256).read_bytes())
    need(
        b["status"] == "PASS_IK_FRONTEND_BUILD"
        and b["ik_commit"] == PIN
        and b["sources"] == result["sources"],
        "build provenance",
    )
    obj = Path(b["objects"])
    for name in FILES:
        pinned(obj / name, b["libraries"][name])
    exe = pinned(a.build / "probe", b["binary_sha256"])
    need(closure(exe, obj) == b["closure"], "live loader")
    vocab = pinned(a.vocab, VOCAB)
    with vocab.open("rb") as f:
        need(
            struct.unpack("<4sIQQ", f.read(24)) == (b"GGUF", 3, 0, 36),
            "vocabulary V3 / zero tensors",
        )
    template = pinned(a.template, FIXED)
    payload = inputs(a.part)
    raw = json.dumps(payload, ensure_ascii=False).encode()
    need(len(raw) < 4 * 2**20, "pipe budget")
    result.update(
        build_sha256=a.build_sha256, archive_sha256=ARCHIVE, vocab_sha256=VOCAB, jinja_sha256=FIXED
    )
    run = subprocess.run(
        [exe, vocab, template],
        env=env(obj),
        preexec_fn=resource_limits,
        input=raw,
        capture_output=True,
        timeout=60,
    )
    result.update(returncode=run.returncode, stderr_sha256=hashlib.sha256(run.stderr).hexdigest())
    if run.returncode:
        phase = re.search(
            rb"private replay failed at (arguments|vocabulary|template|T1|T2)\n", run.stderr
        )
        result["failed_stage"] = phase.group(1).decode() if phase else "native"
        raise ValueError("native replay")
    rows = json.loads(run.stdout)
    need(len(rows) == 2, "replay arms")
    safe = {
        "prompt_bytes",
        "prompt_tokens",
        "sampled",
        "render_difference",
        "ids_difference",
        "direct_ids_difference",
        "date_control",
        "early_eog_rejected",
        "channel_updates",
        "delta_difference",
        "reasoning_equal",
        "final_equal",
        "incomplete_utf8_steps",
    }
    need(
        all(
            isinstance(row, dict)
            and set(row) == safe
            and all(type(v) in (int, bool) for v in row.values())
            for row in rows
        ),
        "public projection",
    )
    result["turns"] = rows
    for row, n, turn in zip(rows, (2043, 2197), payload, strict=True):
        need(
            row["prompt_tokens"] == n
            and row["sampled"] == len(turn["sampled"])
            and row["prompt_bytes"] == len(turn["rendered_prompt"].encode())
            and row["channel_updates"] == len(turn["deltas"])
            and all(
                row[k] == -1
                for k in (
                    "render_difference",
                    "ids_difference",
                    "direct_ids_difference",
                    "delta_difference",
                )
            )
            and all(
                row[k] is True
                for k in ("date_control", "early_eog_rejected", "reasoning_equal", "final_equal")
            ),
            "frontend parity",
        )
    result["status"] = "PASS_IK_C281_FRONTEND_OFFLINE"


def main():
    p = argparse.ArgumentParser()
    subs = p.add_subparsers(dest="mode", required=True)
    build_parser = subs.add_parser("build")
    for key in ("src", "objects"):
        build_parser.add_argument("--" + key, type=Path, required=True)
    verify_parser = subs.add_parser("verify")
    for key in ("part", "build", "vocab", "template"):
        verify_parser.add_argument("--" + key, type=Path, required=True)
    verify_parser.add_argument("--build-sha256", required=True)
    for sub in (build_parser, verify_parser):
        sub.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    result = dict(
        status="FAIL_PRESERVED",
        model_forwards=0,
        sources={
            p.name: sha(p)
            for p in (HERE / "protocol.md", HERE / "probe.cpp", Path(__file__), REFERENCE)
        },
    )
    try:
        (build if a.mode == "build" else verify)(a, out, result)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        struct.error,
    ) as exc:
        # Raw payloads including messages/logits never enter public diagnostics.
        result["error"] = (
            str(exc)
            if type(exc) is ValueError and type(exc).__module__ == "builtins"
            else type(exc).__name__
        )
    (out / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])
    return int(not result["status"].startswith("PASS_"))


if __name__ == "__main__":
    sys.exit(main())
