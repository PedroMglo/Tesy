"""Reproduce the historical C291 image before qualifying a private packed observer."""

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[4]
REPO = QUAL.parents[1]
SONAME = "libllama.so.0"
IMAGE = SONAME + ".0.9884"
TUS = ("llama-context.cpp", "llama-moe-stream.cpp")
TARGET = Path("CMakeFiles/llama.dir")
ORIGINAL = "04af70ea943b816769e2c6d62873ded11f00603df6c3be42340b3785aa880819"
INPUTS = "0297f936aa60f11acb9688e43c358fd692d56250b96a7fb13cab3b3203ff12ec"
PATCH = "44d8dbccb38711a645b0398b4cc73c8cdc19f6c29a77fa31f0f08f111c49700c"
HEADER = "350be0c2ad384c2acbbb06c62eeb9258d011e0c94f8a3d535b2ca82c3ba376a8"
C281 = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"
C292 = "7b0ca3bcc778f527dfc4cdfab3aaa3f93687045cba5e12d5a74b8310aeb7b670"
RECIPES = {
    "link.txt": "1dd184076de82564f8dd3d5a0d31e4d5acc6a46fe3b9420db8e02c4ce6401f1a",
    "flags.make": "5c1b8d87242694e5514a668cebee7ff0d3f11fe5cdc083bfbd8be62b87fca00b",
    "build.make": "eaefa2fc7fa0422a7621925403945ee34c2a79b7bccd1b6ce556594ed0835c37",
}
PIN = "c89c88b342054223e3f27a17fbfd0954803147ac"


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pfj = load(QUAL / "phase_fd/integrated/build.py", "pfj_build")
old = load(QUAL / "stock_prefault_build/build.py", "stock_build")
server = load(QUAL / "packed_nvme_manifest/server_profile/screen.py", "c291_server")
need, sha = pfj.need, pfj.sha
capture = server.capture


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def link(tokens, directory, changed):
    args = tokens.copy()
    dep = "-Wl,--dependency-file=CMakeFiles/llama.dir/link.d"
    need(args[0] == "/usr/bin/c++" and args.count(dep) == args.count("-o") == 1, "link recipe")
    index = args.index("-o") + 1
    need(args[index] == "../bin/" + IMAGE, "unknown output")
    args[index] = str(directory / IMAGE)
    args[args.index(dep)] = "-Wl,--dependency-file=" + str(directory / "link.d")
    for name in changed:
        item = str(TARGET / (name + ".o"))
        need(args.count(item) == 1, "missing TU")
        args[args.index(item)] = str(directory / (name + ".o"))
    return args


def flags(directory):
    definitions = {}
    for line in (directory / "flags.make").read_text().splitlines():
        if line.startswith("CXX_"):
            key, value = line.split(" = ", 1)
            definitions[key] = shlex.split(value)
    return sum((definitions[k] for k in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS")), [])


def section_diff(first, second):
    # Preserve every section including .comment and notes, not just .text.
    def sections(file):
        import re

        blob = file.read_bytes()
        result = {}
        for line in old.captured("readelf", "-SW", file).splitlines():
            m = re.match(
                r"\s*\[\s*\d+\]\s+(\.[^ ]+)\s+(\S+)\s+(\w+)\s+(\w+)\s+(\w+)\s+\w+\s+([A-Z]*)\s",
                line,
            )
            if m:
                name, kind, addr, offset, size, flags = m.groups()
                begin, length = int(offset, 16), int(size, 16)
                data = b"" if kind == "NOBITS" else blob[begin : begin + length]
                result[name] = (flags, addr, length, hashlib.sha256(data).hexdigest())
        need(".text" in result, "ELF section census")
        return result

    x, y = sections(first), sections(second)
    return {k: [x.get(k), y.get(k)] for k in sorted(x.keys() | y.keys()) if x.get(k) != y.get(k)}


def private_sources(backend, directory):
    directory.mkdir()
    src = directory / "src"
    src.mkdir()
    for n in TUS:
        shutil.copyfile(backend / "src" / n, src / n)
    shutil.copyfile(
        QUAL / "phase_fd/integrated/phase-fd-integrated.h", src / "phase-fd-integrated.h"
    )
    subprocess.run(
        [
            "/usr/bin/patch",
            "--batch",
            "--forward",
            "--fuzz=0",
            "-p1",
            "-i",
            str(HERE.parent / "observer.patch"),
        ],
        cwd=directory,
        env=pfj.ENV,
        timeout=10,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    need({p.name for p in src.iterdir()} == {*TUS, "phase-fd-integrated.h"}, "overlay files")
    return src


def run(a, out, r):
    cwd = a.build_root.resolve(strict=True) / "llama"
    rules = cwd / TARGET
    backend = a.backend.resolve(strict=True)
    original = (cwd / "../bin" / IMAGE).resolve(strict=True)
    need(
        pfj.git(HERE, "rev-parse", "HEAD") == a.commit
        and not pfj.git(HERE, "status", "--porcelain"),
        "measurement checkout",
    )
    need(
        pfj.git(backend, "rev-parse", "HEAD") == PIN
        and not pfj.git(backend, "status", "--porcelain"),
        "C291 checkout",
    )
    r.update(
        commit=a.commit,
        tree=pfj.git(HERE, "rev-parse", "HEAD^{tree}"),
        backend_commit=PIN,
        initial_scope=capture.scope(a.unit),
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(__file__),
        original_sha256=sha(original),
        patch_sha256=sha(HERE.parent / "observer.patch"),
        parent_header_sha256=sha(QUAL / "phase_fd/integrated/phase-fd-integrated.h"),
    )
    need(
        r["original_sha256"] == ORIGINAL
        and r["patch_sha256"] == PATCH
        and r["parent_header_sha256"] == HEADER,
        "ELF, pack patch or journal",
    )
    need({k: sha(rules / k) for k in RECIPES} == RECIPES, "original CMake recipes")
    tools = {
        p: sha(p)
        for p in (
            "/usr/bin/c++",
            "/usr/bin/ld",
            "/usr/bin/patch",
            pfj.cmd("/usr/bin/c++", "-print-prog-name=cc1plus"),
            pfj.cmd("/usr/bin/c++", "-print-file-name=crtbeginS.o"),
            pfj.cmd("/usr/bin/c++", "-print-file-name=crtendS.o"),
        )
    }
    need(
        tools["/usr/bin/c++"] == "ca48a2d27d0796399adc3387225eec4be62974e26fa299710edfde0c1af5aa63"
        and tools["/usr/bin/ld"]
        == "eccfdb2b11bcae1ca6e2915a40db609299f46d7def305dab744c0da0aaf54370",
        "compiler or linker",
    )
    r.update(tool_sha256=tools, recipes_sha256=RECIPES)
    tokens = shlex.split((rules / "link.txt").read_text())
    items = [t for t in tokens if t.endswith((".o", "/libggml.so", "/libggml-base.so"))]
    inputs = {t: sha(cwd / t) for t in items}
    need(
        len(inputs) == len(items) == 168 and pfj.stamp(inputs) == INPUTS,
        "166 original objects and the two original provider aliases",
    )
    save(out / "inputs.json", inputs)
    r["inputs_sha256"] = INPUTS
    deadline = time.monotonic() + 280

    def invoke(argv, directory, label):
        save(directory / (label + ".argv.json"), list(map(str, argv)))
        old.produce(
            argv, cwd, directory / (label + ".log"), dict(pfj.ENV, TMPDIR=str(directory)), deadline
        )

    def identical(a, b, label):
        if sha(a) != sha(b):
            r["mismatch"] = dict(
                label=label,
                original_sha256=sha(a),
                actual_sha256=sha(b),
                original_bytes=a.stat().st_size,
                actual_bytes=b.stat().st_size,
                sections=section_diff(a, b),
                original_comment=pfj.cmd("readelf", "-p", ".comment", a),
                actual_comment=pfj.cmd("readelf", "-p", ".comment", b),
            )
            raise ValueError(label + " did not reproduce historical bytes")

    r["stage"] = "intact"
    intact = out / "intact"
    intact.mkdir()
    invoke(link(tokens, intact, ()), intact, "link")
    identical(original, intact / IMAGE, "intact ELF")
    args = flags(rules)
    src = next(t[2:] for t in args if t.startswith("-I") and t.endswith("/src/."))
    need(Path(src).resolve() == backend / "src", "historical include location")
    for mode in ("gold", "candidate"):
        r["stage"] = mode
        d = out / mode
        d.mkdir()
        overlay = private_sources(backend, out / "overlay") if mode == "candidate" else None
        if overlay:
            r["header_sha256"] = sha(overlay / "phase-fd-integrated.h")
            r["overlay_sha256"] = {p.name: sha(p) for p in overlay.iterdir()}
        for name in TUS:
            # Expand the pinned build.make's literal source; preserve literal spelling for __FILE__.
            origin = src.removesuffix("/.") + "/" + name
            target = d / (name + ".o")
            deps = d / (name + ".d")
            options = args.copy()
            if overlay:
                options.insert(0, f"-fmacro-prefix-map={overlay}={src.removesuffix('/.')}")
            invoke(
                [
                    "/usr/bin/c++",
                    *options,
                    "-MD",
                    "-MT",
                    "llama/" + str(TARGET / (name + ".o")),
                    "-MF",
                    str(deps),
                    "-o",
                    str(target),
                    "-c",
                    str(overlay / name) if overlay else origin,
                ],
                d,
                name,
            )
            if mode == "gold":
                identical(rules / (name + ".o"), target, "gold " + name)
            else:
                need(
                    str(overlay / "phase-fd-integrated.h") in deps.read_text(),
                    "private PFJ header missing",
                )
        invoke(link(tokens, d, TUS), d, "link")
        if mode == "gold":
            identical(original, d / IMAGE, "recompiled gold ELF")
            r["gold_sha256"] = sha(d / IMAGE)
    image = out / "candidate" / IMAGE
    r.update(candidate_sha256=sha(image), candidate_file=str(image.relative_to(out)))
    need(
        r["candidate_sha256"] != ORIGINAL and old.abi(image) == old.abi(original),
        "candidate ABI or identity",
    )
    r["stage"] = "closure"
    qualify = load(HERE / "closure.py", "c291_closure")
    qualify.run(server, a, out, original, image, r)
    need(
        all(sha(cwd / t) == v for t, v in inputs.items()) and sha(original) == ORIGINAL,
        "changed historical build",
    )
    r.update(status="PASS_C291_PACK_PFJ_DSO_STATIC_C281", stage="closed")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in (
        "backend",
        "build-root",
        "preflight-dir",
        "c281-closure",
        "c292-closure",
        "new-output-dir",
    ):
        ap.add_argument("--" + k, type=Path, required=True)
    for k in ("unit", "commit"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    need(
        not any(out.is_relative_to(p.resolve()) for p in (a.backend, a.build_root, REPO)),
        "exclusive output outside sources",
    )
    out.mkdir(mode=0o700)
    start = time.monotonic()
    r = dict(status="FAIL_PRESERVED", stage="authenticate", server_starts=0, model_forwards=0)

    def timed_out(*_):
        raise TimeoutError("320 s envelope")

    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(320)
    try:
        run(a, out, r)
        need(
            sum(p.stat().st_size for p in out.rglob("*") if p.is_file() and not p.is_symlink())
            + (1 << 20)
            < 96 << 20,
            "output cap",
        )
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    try:
        r["final_scope"] = capture.scope(a.unit)
        need(r["final_scope"]["memory.peak"] < 2 << 30, "scope peak")
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", scope_error=str(exc))
    r["elapsed_s"] = round(time.monotonic() - start, 6)
    save(out / "receipt.json", r)
    print(r["status"], r["stage"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
