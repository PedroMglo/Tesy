"""Recompile just the stock mmap call site and relink two private libllama images."""

import argparse
import hashlib
import json
import os
import re
import resource
import shlex
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
DSO = "libllama.so.0.9.0"
SONAME = "libllama.so.0"
OBJ = "src/CMakeFiles/llama.dir/llama-model.cpp.o"
SOURCE = "9956da154d2a34fdb2ae627a4c70ef34f046b86c145039de754a7ad7a4b67667"
DB = "66f0c572a796592e7035a5fd0566713939114144c8accedb28cbc86d842ab49a"
NINJA = "9674b5b079330e798acf19ff4fb648b7d2c39fd47b3e97634e3e76f4aee15255"
GCC = "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
CALL = "    ml.init_mappings(true, use_mlock ? &pimpl->mlock_mmaps : nullptr);"


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def patch(text):
    check(
        text.count(CALL) == 1
        and text.count("#include <cstring>") == 1
        and "TESY_STOCK_LAZY_MMAP" not in text,
        "source shape",
    )
    return text.replace("#include <cstring>", "#include <cstring>\n#include <cstdlib>").replace(
        CALL,
        '    const char * lazy = std::getenv("TESY_STOCK_LAZY_MMAP");\n'
        '    if (lazy && std::strcmp(lazy, "0") != 0 && std::strcmp(lazy, "1") != 0) {\n'
        '        throw std::runtime_error("TESY_STOCK_LAZY_MMAP must be 0 or 1");\n    }\n'
        "    ml.init_mappings(!lazy || lazy[0] == '0', use_mlock ? &pimpl->mlock_mmaps : nullptr);",
    )


def captured(*cmd, cwd=None, env=None):
    return subprocess.check_output(
        cmd, cwd=cwd, env=env, text=True, stderr=subprocess.STDOUT, timeout=30
    )


def link_argv(tokens, dest):
    check(
        tokens[:2] == [":", "&&"] and tokens[-2:] == ["&&", ":"] and tokens.count("&&") == 2,
        "Ninja command",
    )
    argv = tokens[2:-2]
    dep = "-Wl,--dependency-file=src/CMakeFiles/llama.dir/link.d"
    check(
        argv[0] == "/usr/bin/g++-15"
        and argv.count(dep) == 1
        and argv.count("-o") == 1
        and argv[argv.index("-o") + 1] == "bin/" + DSO
        and argv.count(OBJ) == 1
        and sum(s.endswith(".o") for s in argv) == 44,
        "unexpected stock link",
    )
    argv[argv.index(dep)] = "-Wl,--dependency-file=" + str(dest / "link.d")
    argv[argv.index("-o") + 1] = str(dest / DSO)
    argv[argv.index(OBJ)] = str(dest / "llama-model.cpp.o")
    return argv


def sections(path):
    blob = path.read_bytes()
    out = {}
    for line in captured("readelf", "-SW", path).splitlines():
        m = re.match(
            r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+(\w+)\s+(\w+)\s+(\w+)\s+\w+\s+([A-Z]+)\s", line
        )
        if m and "A" in m[6]:
            name, kind, addr, offset, size, flags = m.groups()
            start, n = int(offset, 16), int(size, 16)
            b = b"" if kind == "NOBITS" else blob[start : start + n]
            out[name] = [addr, size, flags, hashlib.sha256(b).hexdigest()]
    check(".text" in out and ".dynamic" in out, "ELF sections")
    return out


def abi(path):
    syms = []
    for line in captured("nm", "-D", "--defined-only", "--format=posix", path).splitlines():
        name, kind, *values = line.split()
        # Size is ABI-relevant for exported data. Function addresses/sizes may change.
        syms.append([name, kind, values[-1] if kind.upper() in {"B", "D", "R", "S", "G"} else None])
    dynamic = [
        line.split("]", 1)[0].split("[", 1)[-1]
        for line in captured("readelf", "-d", path).splitlines()
        if any(tag in line for tag in ("(NEEDED)", "(SONAME)", "(RUNPATH)", "(RPATH)"))
    ]
    return {
        "exports": len(syms),
        "exports_sha256": hashlib.sha256(json.dumps(sorted(syms)).encode()).hexdigest(),
        "dynamic": dynamic,
    }


def limited():
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (min(2 * 2**30, hard) if hard >= 0 else 2 * 2**30, hard))


def produce(argv, cwd, log, env, deadline):
    with log.open("xb") as f:
        subprocess.run(
            argv,
            cwd=cwd,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
            env=env,
            timeout=max(0.1, deadline - time.monotonic()),
            preexec_fn=limited,
        )


def run(root, out, receipt):
    b = root / "build"
    source = root / "source/src/llama-model.cpp"
    original = b / "bin" / DSO
    stock = json.loads((QUAL / "stock_build/attempt-b/receipt.json").read_bytes())
    check(
        captured("git", "-C", root / "source", "rev-parse", "HEAD").strip() == stock["pin"]
        and not captured(
            "git", "-C", root / "source", "status", "--porcelain", "--untracked-files=no"
        ).strip(),
        "stock source identity",
    )
    check(
        sha(source) == SOURCE
        and sha(b / "compile_commands.json") == DB
        and sha(b / "build.ninja") == NINJA
        and sha("/usr/bin/g++-15") == GCC,
        "compiler, source or Ninja inputs",
    )
    env = {**os.environ, "LC_ALL": "C", "TMPDIR": str(out), "OMP_NUM_THREADS": "1"}
    env.pop("LD_PRELOAD", None)
    env.pop("TESY_STOCK_LAZY_MMAP", None)
    for name, h in stock["own_libs_sha256"].items():
        check(sha(b / "bin" / name) == h, "stock DSO " + name)
    server = b / "bin/llama-server"
    check(sha(server) == stock["server_sha256"], "stock server")
    (row,) = [
        c
        for c in json.loads((b / "compile_commands.json").read_bytes())
        if Path(c["file"]) == source
    ]
    compile_cmd = shlex.split(row["command"])
    check(
        Path(row["directory"]) == b and compile_cmd[-4:] == ["-o", OBJ, "-c", str(source)],
        "stock compile",
    )
    tokens = shlex.split(
        captured("ninja", "-C", b, "-t", "commands", "bin/" + DSO).splitlines()[-1]
    )
    inputs = {
        s: sha(b / s)
        for s in tokens
        if s.endswith(".o") or ".so" in s and not s.startswith("-") and s != "bin/" + DSO
    }
    receipt.update(
        original_sha256=sha(original),
        server_sha256=sha(server),
        inputs=inputs,
        original_abi=abi(original),
        compile_commands_sha256=DB,
        ninja_sha256=NINJA,
        compiler_sha256=GCC,
        source_sha256=SOURCE,
        stock_dsos=stock["own_libs_sha256"],
        phases={},
    )
    for mode in ("gold", "candidate"):
        dest = out / mode
        dest.mkdir()
        deadline = time.monotonic() + 120
        cc = compile_cmd.copy()
        cc[cc.index("-o") + 1] = str(dest / "llama-model.cpp.o")
        if mode == "candidate":
            private = dest / "llama-model.cpp"
            private.write_text(patch(source.read_text()))
            cc[1:1] = [f"-fmacro-prefix-map={dest}={source.parent}"]
            cc[-1] = str(private)
        ld = link_argv(tokens, dest)
        (dest / "argv.json").write_text(json.dumps([cc, ld], indent=2) + "\n")
        produce(cc, b, dest / "compile.log", env, deadline)
        produce(ld, b, dest / "link.log", env, deadline)
        image = dest / DSO
        (dest / SONAME).symlink_to(DSO)
        (dest / "libllama.so").symlink_to(DSO)
        a, o = sections(image), sections(original)
        differences = [name for name in sorted(set(a) | set(o)) if a.get(name) != o.get(name)]
        result = {
            "sha256": sha(image),
            "object_sha256": sha(dest / "llama-model.cpp.o"),
            "stock_object_sha256": sha(b / OBJ),
            "alloc_sections_differ": differences,
            "abi": abi(image),
            "input_source_sha256": sha(cc[-1]),
            "log_sha256": {f.name: sha(f) for f in dest.glob("*.log")},
            "argv_sha256": sha(dest / "argv.json"),
        }
        receipt["phases"][mode] = result
        if mode == "gold":
            check(result["sha256"] == sha(original), "gold DSO not byte-identical")
        else:
            check(result["sha256"] != sha(original), "candidate DSO unchanged")
        check(result["abi"] == receipt["original_abi"], "exported ABI or dynamic dependencies")
        runtime = {**env, "LD_LIBRARY_PATH": str(dest) + ":" + str(b / "bin")}
        listing = captured("/lib64/ld-linux-x86-64.so.2", "--list", server, env=runtime)
        check(f"{SONAME} => {dest / SONAME} " in listing, "private DSO missing from loader map")
        result["version"] = captured(server, "--version", env=runtime).splitlines()
        check(result["version"] == stock["version_lines"], "stock version")
        result["elapsed_s"] = round(time.monotonic() - (deadline - 120), 3)
    check(
        all(sha(b / s) == h for s, h in inputs.items())
        and sha(original) == receipt["original_sha256"],
        "stock inputs changed",
    )
    receipt["status"] = "PASS_PRIVATE_GOLD_AND_CANDIDATE_BUILD"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-build-root", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    root, out = a.stock_build_root.resolve(), a.new_output_dir.resolve()
    check(not out.is_relative_to(root), "private output inside original build")
    out.mkdir(mode=0o700)
    result = {"status": "FAIL_PRESERVED", "scope": "BUILD_ONLY_NO_FORWARD"}
    try:
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "index.threads=1",
            "-c",
            "core.preloadIndex=false",
            "-C",
            HERE,
        ]
        result.update(
            measurement_commit=captured(*git, "rev-parse", "HEAD").strip(),
            measurement_tree=captured(*git, "rev-parse", "HEAD^{tree}").strip(),
            clean_before_build=not captured(
                *git, "status", "--porcelain=v1", "--untracked-files=normal"
            ).strip(),
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
        )
        check(result["clean_before_build"], "dirty measurement checkout")
        run(root, out, result)
        result["new_output_bytes"] = sum(
            f.stat().st_size for f in out.rglob("*") if f.is_file() and not f.is_symlink()
        )
        check(result["new_output_bytes"] <= 150 * 2**20 - 65536, "build output budget")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result.update(status="FAIL_PRESERVED", error=str(exc))
    (out / "receipt.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
