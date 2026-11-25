"""Build three isolated four-row probes against the verified C269 CPU backend."""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mxfp4_vnni"))
import build_native as pin  # noqa: E402

SYMBOL = "tesy_four_rows"
ARMS = ("control", "shared", "separate")


def pinned_headers(src):
    prefix = src[: src.index("#if defined(__AVX__) ||")]
    return "\n".join(
        (
            prefix,
            "#ifndef __AVX2__\n#error AVX2 required\n#endif",
            pin.function(src, "static inline float hsum_float_8("),
            pin.function(src, "static inline __m256i mul_add_epi8("),
        )
    )


def instructions(asm):
    rows = []
    for line in asm.splitlines():
        match = re.match(r"^\s*([0-9a-f]+):\s+(?:\{\w+\}\s+)*(\w+)\s*(.*?)\s*$", line)
        if match:
            rows.append((int(match[1], 16), match[2], match[3]))
    return rows


def hot_loop(rows):
    # Only a backward control-flow edge spanning all eight pairs of byte
    # multiply/sums can be the complete four-row, two-block iteration.
    candidates = []
    for end, operation, operands in rows:
        target = re.match(r"^([0-9a-f]+) <", operands)
        if not operation.startswith("j") or not target:
            continue
        start = int(target[1], 16)
        if start >= end:
            continue
        body = [row for row in rows if start <= row[0] <= end]
        if sum(op == "vpmaddubsw" for _, op, _ in body) == 8:
            candidates.append(body)
    pin.require(candidates, "no four-row arithmetic inside backward loop")
    return min(candidates, key=len)


def inspect(elf, arm, out):
    raw = pin.run(
        "objdump", "-d", "--no-show-raw-insn", "-M", "intel", "--disassemble=" + SYMBOL, elf
    )
    (out / (arm + ".asm")).write_text(raw)
    rows = instructions(raw)
    calls = [args for _, op, args in rows if op in {"call", "jmp"} and pin.SYMBOL in args]
    pin.require(calls, f"{arm}: expected R0 fallback call")
    item = {
        "elf_sha256": pin.sha(elf),
        "instructions": len(rows),
        "r0_static_call_sites": len(calls),
    }
    if arm == "control":
        pin.require(not any(op.startswith("vfmadd") for _, op, _ in rows), "control contains dot")
        return item

    body = hot_loop(rows)
    raw_loop = "\n".join(f"{addr:x} {op} {ops}" for addr, op, ops in body) + "\n"
    (out / (arm + ".loop.asm")).write_text(raw_loop)
    counts = Counter(op for _, op, _ in body)
    fp_fmas = [args for _, op, args in body if re.fullmatch(r"vfmadd\d+ps", op)]
    pin.require(len(fp_fmas) == 8, f"{arm}: expected eight vector FMAs")
    for op, expected in (("vpmaddubsw", 8), ("vpmaddwd", 8), ("vcvtdq2ps", 8), ("vpshufb", 16)):
        pin.require(counts[op] == expected, f"{arm}: observed {counts[op]} {op}")
    pin.require(not any("vpdp" in op for _, op, _ in rows), f"{arm}: VNNI unexpectedly emitted")
    frame = any(op == "mov" and args.startswith("rbp,rsp") for _, op, args in rows)
    stack = r"\[(?:rsp|rbp)\b" if frame else r"\[rsp\b"
    stack_access = [(op, args) for _, op, args in body if re.search(stack, args)]
    # The 17-byte MXFP4 blocks load packed codes with 128-bit reads. Only
    # the 34-byte Q8 block has a 256-bit code load and a uint16 scale index.
    code_reads = [
        args
        for _, op, args in body
        if op.startswith(("vmovdqu", "vmovups"))
        and re.match(r"ymm\d+,YMMWORD PTR \[", args)
        and not re.search(stack, args)
    ]
    scale_reads = [
        args
        for _, op, args in body
        if op == "movzx" and ",WORD PTR [" in args and not re.search(stack, args)
    ]
    return {
        **item,
        "hot_instructions": len(body),
        "hot_assembly_sha256": hashlib.sha256(raw_loop.encode()).hexdigest(),
        "q8_code_loads": code_reads,
        "q8_scale_index_loads": scale_reads,
        "fmadd": fp_fmas,
        "stack_accesses": stack_access,
        "frame_pointer": frame,
        "arithmetic": {
            k: counts[k]
            for k in ("vpshufb", "vpsignb", "vpmaddubsw", "vpmaddwd", "vcvtdq2ps", "vpdpbusd")
        },
    }


def build(backend, out):
    backend = backend.resolve(strict=True)
    database = backend / "build-c269-cuda/compile_commands.json"
    original = database.parent / "bin/libggml-cpu.so.0.15.3"
    source = backend / pin.SOURCE
    pin.require(pin.run("git", "-C", backend, "rev-parse", "HEAD").strip() == pin.PIN, "pin")
    pin.require(
        not pin.run("git", "-C", backend, "status", "--porcelain", "--", "ggml"),
        "dirty backend ggml",
    )
    for path, sha in (
        (database, pin.DATABASE_SHA),
        (original, pin.R0_SHA),
        (source, pin.SOURCE_SHA),
    ):
        pin.require(pin.sha(path) == sha, f"wrong {path.name}")
    (entry,) = [
        row
        for row in json.loads(database.read_text())
        if row["file"].endswith("/" + str(pin.SOURCE))
    ]
    cmd = shlex.split(entry["command"])
    cc = Path(cmd[0])
    pin.require(cc == Path("/usr/bin/gcc-15"), "compiler path")
    old_root = entry["file"].removesuffix(str(pin.SOURCE)).rstrip("/")
    flags = [a.replace(old_root, str(backend)) for a in cmd[1 : cmd.index("-o")]]
    pin.require({"-march=native", "-O3", "-std=gnu11", "-fPIC"}.issubset(flags), "flags")
    header = out / "private-pinned.h"
    header.write_text(pinned_headers(source.read_text()))
    exports = out / "symbols.map"
    exports.write_text("{ global: " + SYMBOL + "; local: *; };\n")
    receipt = {
        "pin": pin.PIN,
        "ggml_cpu_sha256": pin.R0_SHA,
        "ggml_quants_sha256": pin.SOURCE_SHA,
        "database_sha256": pin.DATABASE_SHA,
        "gcc_sha256": pin.sha(cc),
        "c_sha256": pin.sha(HERE / "four_rows.c"),
        "header_sha256": pin.sha(header),
        "gcc": pin.run(cc, "--version").splitlines()[0],
        "arms": {},
    }
    for idx, arm in enumerate(ARMS):
        elf = out / (arm + ".so")
        command = [
            cc,
            *flags,
            "-I",
            out,
            "-iquote",
            source.parent,
            "-DTESY_FOUR_MODE=" + str(idx),
            "-shared",
            HERE / "four_rows.c",
            "-Wl,--no-undefined",
            "-Wl,--version-script=" + str(exports),
            "-Wl,-rpath," + str(original.parent),
            original,
            "-o",
            elf,
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        defined = pin.run("nm", "-D", "--defined-only", elf).splitlines()
        pin.require([s.split()[-1] for s in defined] == [SYMBOL], f"{arm}: ABI")
        undefined = set(pin.run("nm", "-D", "--undefined-only", elf).split())
        pin.require(pin.SYMBOL in undefined, f"{arm}: original dot absent")
        if idx:
            pin.require(pin.TABLES <= undefined, f"{arm}: shared conversion tables absent")
        receipt["arms"][arm] = {**inspect(elf, arm, out), "command": list(map(str, command))}
    for arm, expected in (("shared", 2), ("separate", 8)):
        data = receipt["arms"][arm]
        for name in ("q8_code_loads", "q8_scale_index_loads"):
            pin.require(len(data[name]) == expected, f"{arm}: unexpected {name}: {data[name]}")
    return {**receipt, "status": "PASS_BUILD_FOUR_ROW_DISASSEMBLY"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.absolute()
    out.mkdir(exist_ok=False)
    try:
        result = build(args.backend, out)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        (out / "build.json").write_text(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": str(exc),
                    "stderr": getattr(exc, "stderr", None),
                },
                indent=2,
            )
            + "\n"
        )
        raise
    (out / "build.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])
