"""Rebuild two C269 objects privately and verify the C270/C281 startup closures."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import shlex
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1]
WORKER = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
IMAGE = "libllama.so.0.0.9884"
ORIGINAL = "347267b2e9cbf920dbf912d6aaf1884e5eff4cccc41c349e93c42bd6403a658f"
SONAME = "libllama.so.0"
PREFLIGHT = "2508e245fcde7ff411c93474919c3701ac95e98c1f76505d74a248d34a6aff16"
DB = "2582285bc2b5b7af91570e5c9f4ca326c34bdc6da2ec7aef53ce87c393f6fb6c"
NINJA = "34c0ff3554a9637e3829131a641ff799fc04b94051d9c71999a95eacb6381d21"
RULES = "049f8d12e3b9f38440a4169cbf76753d3acd78cdd2dab53ac4bfe7ed731842ff"
LINK = "3b9a1cf788b922579af65554e7a4db1c5930368a14774d8bfe3328e8e3844bb2"
INPUTS = "550fc4cec9270d2681080ebad66ff037c5c23997b3adfb7f467363b93e1f338e"
CTX = "src/llama-context.cpp"
MGR = "src/llama-moe-stream.cpp"
SOURCES = {
    CTX: "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
    MGR: "584aecb73900aa1164f00ec93126bc5b8b07c4d330d0f421641331b0c278d5a0",
}
CXX = "/usr/bin/g++-15"
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def stamp(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cmd(*args, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env or ENV, text=True, timeout=30).strip()


def git(path, *args):
    return cmd(
        "git",
        "--no-optional-locks",
        "-c",
        "index.threads=1",
        "-c",
        "core.preloadIndex=false",
        "-C",
        path,
        *args,
    )


def obj(source):
    return "src/CMakeFiles/llama.dir/" + Path(source).name + ".o"


def link_args(tokens, dest):
    dep = "-Wl,--dependency-file=src/CMakeFiles/llama.dir/link.d"
    need(
        tokens[:3] == [":", "&&", CXX] and tokens[-2:] == ["&&", ":"] and tokens.count("&&") == 2,
        "Ninja link grammar",
    )
    args = tokens[2:-2]
    need(
        args.count(dep) == args.count("-o") == 1 and args[args.index("-o") + 1] == "bin/" + IMAGE,
        "link output",
    )
    args[args.index(dep)] = "-Wl,--dependency-file=" + str(dest / "link.d")
    args[args.index("-o") + 1] = str(dest / IMAGE)
    for name in SOURCES:
        old = obj(name)
        need(args.count(old) == 1, "affected object count")
        args[args.index(old)] = str(dest / Path(old).name)
    return args


def symbols(path):
    result = {}
    for row in cmd("nm", "-D", "--defined-only", "--format=posix", path).splitlines():
        name, kind, *values = row.split()
        need(name not in result, "duplicate symbol")
        result[name] = [kind, values[-1] if kind.upper() in {"B", "D", "R", "S", "G"} else None]
    return result


def abi_subset(before, after):
    need(all(after.get(name) == value for name, value in before.items()), "existing ABI changed")
    return sorted(after.keys() - before.keys())


def verify(arm, mode, image, expected, authority, static, files):
    name = mode or "original"
    search = arm["native_search"]
    if mode:
        search = [str(image.parent), *search]
    env = static.environment(search)
    links = static.interpret(cmd(static.LOADER, "--list", arm["executable"], env=env))
    need(
        links.keys() == expected.keys() == arm["links"].keys(), "different startup objects: " + name
    )
    result = {}
    for key, path in links.items():
        target = image if mode and key == SONAME else Path(arm["links"][key][1])
        digest = authority if mode and key == SONAME else expected[key]["sha256"]
        real = files.require(path, digest)
        need(real == target.resolve(strict=True), "foreign startup provider: " + key)
        result[key] = {"file": real.name, "sha256": digest}
    return result


def build(backend, preflight, out, record):
    stock = module(QUAL / "stock_prefault_build/build.py", "phase_private_build")
    native = module(HERE / "native.py", "phase_integrated_patch")
    static = module(QUAL / "nvme_r0_gate/driver_pair/server_startup/screen.py", "phase_static")
    b = backend / "build-c269-cuda"
    original = b / "bin" / IMAGE
    need(
        not git(HERE, "status", "--porcelain")
        and not git(backend, "status", "--porcelain")
        and git(backend, "rev-parse", "HEAD") == WORKER,
        "dirty or wrong checkout",
    )
    record.update(
        commit=git(HERE, "rev-parse", "HEAD"),
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        worker_commit=WORKER,
        original_sha256=ORIGINAL,
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(__file__),
        patch_program_sha256=sha(HERE / "native.py"),
        static_preflight_sha256=PREFLIGHT,
    )
    need(sha(preflight / "receipt.json") == PREFLIGHT, "preflight")
    pre = json.loads((preflight / "receipt.json").read_bytes())
    need(
        sha(preflight / "static-map.json") == pre["static_map_sha256"]
        and sha(Path(static.__file__)) == pre["source_sha256"]
        and pre["status"] == "PASS_STATIC_C270_C281_DRIVER_SELECTION",
        "map and helper",
    )
    arms = json.loads((preflight / "static-map.json").read_bytes())["arms"]
    need(
        sha(original) == ORIGINAL
        and sha(CXX) == stock.GCC
        and sha(b / "compile_commands.json") == DB
        and sha(b / "build.ninja") == NINJA
        and sha(b / "CMakeFiles/rules.ninja") == RULES,
        "backend build inputs",
    )
    need(all(sha(backend / src) == h for src, h in SOURCES.items()), "upstream TU")
    tokens = shlex.split(cmd("ninja", "-C", b, "-t", "commands", "bin/" + IMAGE).splitlines()[-1])
    need(stamp(tokens) == LINK, "link recipe")
    inputs = [
        s
        for s in tokens
        if s.endswith(".o") or (not s.startswith("-") and ".so" in s and s != "bin/" + IMAGE)
    ]
    manifest = {s: sha(b / s) for s in inputs}
    need(
        len(manifest) == len(inputs) == 171 and stamp(manifest) == INPUTS, "object and link inputs"
    )
    (out / "inputs.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    static_files = static.Files()
    original_abi = stock.abi(original)
    original_defs = symbols(original)
    for arm in arms.values():
        need(sha(arm["executable"]) == arm["executable_sha256"], "original executable")
    record.update(
        inputs_sha256=INPUTS,
        link_command_sha256=LINK,
        original_source_sha256=SOURCES,
        cc_db_sha256=DB,
        ninja_sha256=NINJA,
        rules_sha256=RULES,
        compiler_sha256=stock.GCC,
        cc1plus_sha256=sha(cmd(CXX, "-print-prog-name=cc1plus")),
        compiler_version=cmd(CXX, "-dumpfullversion"),
        linker_sha256=sha("/usr/bin/ld"),
        object_count=sum(s.endswith(".o") for s in inputs),
        reused_object_count=164,
        startup={
            k: {
                "original": verify(
                    v, None, original, pre["arms"][k]["objects"], ORIGINAL, static, static_files
                )
            }
            for k, v in arms.items()
        },
        phases={},
    )
    overlay = out / "overlay"
    overlay.mkdir()
    changed = native.materialize(backend, overlay)
    expected = {overlay / s for s in SOURCES} | {overlay / "src/phase-fd-integrated.h"}
    need(
        set(changed) == SOURCES.keys()
        and all(changed[s] == overlay / s for s in SOURCES)
        and {p for p in overlay.rglob("*") if p.is_file()} == expected,
        "unexpected source layout",
    )
    record["overlay_sha256"] = {str(p.relative_to(overlay)): sha(p) for p in sorted(expected)}
    database = json.loads((b / "compile_commands.json").read_bytes())
    for mode in ("gold", "candidate"):
        phase = out / mode
        phase.mkdir()
        record["stage"] = mode
        commands = []
        env = dict(ENV, TMPDIR=str(phase))
        limit = time.monotonic() + 180
        objs = {}
        for src in SOURCES:
            source = backend / src
            (row,) = [r for r in database if Path(r["file"]).resolve() == source]
            cc = shlex.split(row["command"])
            need(
                Path(row["directory"]).resolve() == b
                and cc[0] == CXX
                and cc[-4:] == ["-o", obj(src), "-c", row["file"]],
                "unrecognized compile recipe",
            )
            cc[-3] = str(phase / Path(obj(src)).name)
            if mode == "candidate":
                cc[1:1] = [f"-fmacro-prefix-map={overlay / 'src'}={Path(row['file']).parent}"]
                cc[-1] = str(changed[src])
            commands.append(cc)
            stock.produce(cc, b, phase / (Path(src).stem + ".log"), env, limit)
            objs[src] = sha(phase / Path(obj(src)).name)
            if mode == "gold":
                need(objs[src] == manifest[obj(src)], "gold object mismatch: " + src)
        ld = link_args(tokens, phase)
        commands.append(ld)
        (phase / "argv.json").write_text(json.dumps(commands, indent=2) + "\n")
        stock.produce(ld, b, phase / "link.log", env, limit)
        image = phase / IMAGE
        (phase / SONAME).symlink_to(IMAGE)
        digest = sha(image)
        need((digest == ORIGINAL) == (mode == "gold"), "gold/candidate identity")
        additions = abi_subset(original_defs, symbols(image))
        abi = stock.abi(image)
        need(abi["dynamic"] == original_abi["dynamic"], "link ABI changed")
        record["phases"][mode] = {
            "abi": abi,
            "additional_exports": additions,
            "objects": objs,
            "command_sha256": sha(phase / "argv.json"),
        }
        record[mode + "_sha256"] = digest
        record[mode + "_file"] = str(image.relative_to(out))
        for key, arm in arms.items():
            record["startup"][key][mode] = verify(
                arm, mode, image, pre["arms"][key]["objects"], digest, static, static_files
            )
    need(
        all(sha(b / s) == h for s, h in manifest.items()) and sha(original) == ORIGINAL,
        "changed inputs",
    )
    record.update(stage="done", status="PASS_C269_PHASE_FD_PRIVATE_BUILD")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("backend", "preflight-dir", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    backend = a.backend.resolve(strict=True)
    need(
        not out.is_relative_to(backend) and not out.is_relative_to(QUAL.parents[1]),
        "private output",
    )
    out.mkdir(mode=0o700)
    start = time.monotonic()
    record = {
        "status": "FAIL_PRESERVED",
        "stage": "authenticate",
        "server_starts": 0,
        "model_forwards": 0,
    }
    try:
        build(backend, a.preflight_dir, out, record)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as e:
        record["error_type"] = type(e).__name__
        (out / "error.txt").write_text(str(e) + "\n")
    record.update(
        elapsed_s=round(time.monotonic() - start, 6),
        max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        output_bytes_before_receipt=sum(
            f.stat().st_size for f in out.rglob("*") if f.is_file() and not f.is_symlink()
        ),
    )
    tmp = out / "receipt.json.tmp"
    tmp.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    os.replace(tmp, out / "receipt.json")
    print(record["status"], record["stage"])
    return int(record["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
