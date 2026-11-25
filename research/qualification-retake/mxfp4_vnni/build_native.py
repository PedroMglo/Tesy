"""Build the isolated C269 MXFP4 dot paths and inspect their machine code."""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path

PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
SOURCE = Path("ggml/src/ggml-cpu/arch/x86/quants.c")
SYMBOL = "ggml_vec_dot_mxfp4_q8_0"
SOURCE_SHA = "3c489fdc77e3ab484a5f188bff9c60c0e9483c951ed65c1a562a04c249d5628e"
DATABASE_SHA = "2582285bc2b5b7af91570e5c9f4ca326c34bdc6da2ec7aef53ce87c393f6fb6c"
R0_SHA = "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313"
TABLES = {"ggml_table_f32_e8m0_half", "ggml_table_f32_f16"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def require(condition, message):
    if not condition:
        raise ValueError(message)


def function(source, declaration):
    start = source.index("\n" + declaration) + 1
    stop = source.index("\n}", start) + 2
    return source[start:stop] + "\n"


def isolate(source):
    # Emit original definitions with their headers. Only AVX2-capable x86
    # builds are admitted. Even the fallback retains AVX2 and its scalar tail.
    prefix = source[: source.index("#if defined(__AVX__) ||")]
    body = [prefix, "#ifndef __AVX2__\n#error AVX2 required\n#endif\n"]
    for item in (
        "static inline float hsum_float_8(",
        "static inline __m256i mul_add_epi8(",
        "static inline __m256 sum_i16_pairs_float(",
        "static inline __m256 mul_sum_us8_pairs_float(",
        "void " + SYMBOL + "(",
    ):
        body.append(function(source, item))
    return "\n".join(body)


def inspect(elf, destination, vnni):
    asm = run("objdump", "-d", "--no-show-raw-insn", "-M", "intel", "--disassemble=" + SYMBOL, elf)
    destination.write_text(asm)
    ops = re.findall(r"^\s*[0-9a-f]+:\s+(?:\{\w+\}\s+)*(\w+)", asm, re.M)
    counts = Counter(ops)
    gate = {
        "vpshufb": 4,
        "vpsignb": 4,
        "vcvtdq2ps": 2,
        "vpdpbusd": 2 if vnni else 0,
        "vpmaddubsw": 0 if vnni else 2,
        "vpmaddwd": 0 if vnni else 2,
    }
    require(
        all(counts[k] == v for k, v in gate.items()), f"{elf.name}: expected {gate}, got {counts}"
    )
    fma = sum(v for k, v in counts.items() if re.fullmatch(r"vfmadd\d+ps", k))
    require(fma == 2, f"{elf.name}: expected two vector FMAs, saw {fma}")
    return {
        "sha256": sha(elf),
        "ops": gate,
        "vector_fma": fma,
        "instructions": len(ops),
        "mnemonics_sha256": hashlib.sha256("\n".join(ops).encode()).hexdigest(),
    }


def build(backend, out):
    out = out.absolute()
    out.mkdir(exist_ok=False)
    backend = backend.resolve(strict=True)
    builddir = backend / "build-c269-cuda"
    source = backend / SOURCE
    original = builddir / "bin/libggml-cpu.so.0.15.3"
    database = builddir / "compile_commands.json"
    require(run("git", "-C", backend, "rev-parse", "HEAD").strip() == PIN, "backend commit")
    require(
        not run("git", "-C", backend, "status", "--porcelain", "--", "ggml"), "dirty backend ggml"
    )
    for path, expected in ((source, SOURCE_SHA), (original, R0_SHA), (database, DATABASE_SHA)):
        require(sha(path) == expected, f"{path.name}: pinned digest")
    patch = Path(__file__).with_name("candidate.patch").resolve()
    patched = out / "patched-full.c"
    run("patch", "--batch", "--fuzz=0", "--output", patched, source, patch)
    rows = [
        entry
        for entry in json.loads(database.read_text())
        if entry["file"].endswith("/" + str(SOURCE))
    ]
    require(len(rows) == 1, "compile database has ambiguous x86 quants entry")
    cmd = shlex.split(rows[0]["command"])
    cc = Path(cmd[0])
    require(cc == Path("/usr/bin/gcc-15"), "unexpected compiler")
    flags = cmd[1 : cmd.index("-o")]
    # Use the sealed flags and resolve any relocated source root in -I paths.
    previous_root = rows[0]["file"].removesuffix(str(SOURCE)).rstrip("/")
    flags = [f.replace(previous_root, str(backend)) for f in flags]
    required_flags = {"-march=native", "-O3", "-std=gnu11", "-fPIC"}
    require(required_flags.issubset(flags), "compile flags")
    exports = out / "exports.map"
    exports.write_text("{ global: " + SYMBOL + "; local: *; };\n")
    receipt = {
        "pin": PIN,
        "source_sha256": SOURCE_SHA,
        "compile_database_sha256": DATABASE_SHA,
        "patch_sha256": sha(patch),
        "gcc_sha256": sha(cc),
        "gcc": run(cc, "--version").splitlines()[0],
        "symbol": SYMBOL,
        "r0": inspect(original, out / "r0.asm", False),
        "arms": {},
    }
    for name in ("control", "candidate", "fallback"):
        cfile = out / (name + ".c")
        cfile.write_text(isolate((source if name == "control" else patched).read_text()))
        elf = out / (name + ".so")
        arm_flags = (
            ["-march=haswell", "-mno-avxvnni", "-mno-avx512vnni"] if name == "fallback" else []
        )
        command = [
            cc,
            *flags,
            *arm_flags,
            "-iquote",
            source.parent,
            "-shared",
            cfile,
            "-Wl,--no-undefined",
            "-Wl,--version-script=" + str(exports),
            "-Wl,-rpath," + str(original.parent),
            original,
            "-o",
            elf,
        ]
        run(*command)
        defined = run("nm", "-D", "--defined-only", elf).splitlines()
        require(
            [line.split()[-1] for line in defined] == [SYMBOL], f"{name}: wrong exported symbol"
        )
        undefined = set(run("nm", "-D", "--undefined-only", elf).split())
        require(TABLES <= undefined, f"{name}: pinned conversion tables not imported")
        receipt["arms"][name] = {
            **inspect(elf, out / (name + ".asm"), name == "candidate"),
            "c_source_sha256": sha(cfile),
            "command": list(map(str, command)),
        }
    fallback_asm = run("objdump", "-d", "-w", "--disassemble=" + SYMBOL, out / "fallback.so")
    require(not re.search(r"^\s*[0-9a-f]+:\s+62 ", fallback_asm, re.M), "fallback has EVEX")
    receipt["fallback_no_evex"] = True
    receipt["control_matches_r0_mnemonics"] = (
        receipt["arms"]["control"]["mnemonics_sha256"] == receipt["r0"]["mnemonics_sha256"]
    )
    receipt["status"] = "PASS_BUILD_DISASSEMBLY_ONLY"
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.backend, args.out)
    except FileExistsError:
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        failure = {"status": "FAIL", "error": str(exc), "stderr": getattr(exc, "stderr", "")}
        if args.out.is_dir():
            (args.out / "build.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise
    (args.out / "build.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])
