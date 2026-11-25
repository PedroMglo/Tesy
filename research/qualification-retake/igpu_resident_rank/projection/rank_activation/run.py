"""Build only GLSL or run four activation segments and the original C269 quantizer."""

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IGPU = HERE.parents[1]
RHS = IGPU / "rhs_device"
sys.path.insert(0, str(HERE))
import grade  # noqa: E402

OLD_BUILD = "8a3171e81809f8a1b151c3a3f5ad025320e91a67a283ae6eb52880ad8c728e75"
OLD_DEVICE = "472fa699385b57fc56df08c48264f0bb39ba8731365c3adc6b581858e2e45edd"
GOLD = "3ef107129e6d4c7afb755ac5836c9099b37a37f3eb3ab87f25fed3e9ba28dd53"
ORDER = "01a5f5d1bc068891154722eb5c0b5663d100e084e82b32bf6a6c7a99957cb7f5"
OPS = "ae3553e5e7773ac4205ac07216e35619230b605a07c2091a3eaf5c6647243cc7"
DEPS = {
    RHS / "run.py": "73f636fa0d835cc2e5b39bf5b921f7ad2f164a4660c08126bc314f52e95fb8fb",
    RHS / "compile_shader.py": "32dfe380d9e35e8baf64ca138b4395f3f50fb6d5c5ef82a4aa194f2d25e6a482",
    IGPU / "run.py": "b27537f659684c90d9adea6eeb58cb63c9299aa93a07f1a556f9b9ea60e4d8c9",
    HERE.parent
    / "rank_cpu/grade.py": "007ee67dad130131c6a7bb42e7a1f885222ab16293abb3087b8c2928fd79bad7",
    HERE.parent
    / "reference/arithmetic.py": "f69971181e20e326f1efcb6f070454180f5faa90baeac743152fe17650a87c53",
}


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sealed(path, expected):
    need(
        path.is_file() and not path.is_symlink() and digest(path) == expected,
        "identity " + path.name,
    )


def save(path, content):
    with path.open("x") as file:
        json.dump(content, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")


def authorities(a):
    for path, expected in DEPS.items():
        sealed(path, expected)
    rhs = run_path(RHS / "run.py")
    host = rhs["BASE"]
    environment = host["seals"]()
    old = a.rhs_build.resolve(strict=True)
    sealed(old / "receipt.json", OLD_BUILD)
    proof = json.loads((old / "receipt.json").read_bytes())
    need(
        proof["status"] == "PASS_RHS_BUILD_ONLY" and proof["headers"] == host["HEADERS"], "headers"
    )
    for name in ("dispatch", "shared.spv", "subgroup.spv"):
        sealed(old / name, proof["files"][name])
    for name, expected in proof["headers"].items():
        sealed(a.headers / "vulkan" / name, expected)
    sealed(RHS / "evidence/receipt.json", OLD_DEVICE)
    sealed(HERE.parent / "ordered_dot/receipt.json", ORDER)
    order = json.loads((HERE.parent / "ordered_dot/receipt.json").read_bytes())
    need(
        order["files"]["correct.f32"]
        == "756c8384a4cda89c62040a81d3e45dd06e0707121dcbadecc73d45ecec0e1db3",
        "ordered gate equations",
    )
    return rhs, environment, old, proof


def reflect(blob):
    words = struct.unpack("<" + str(len(blob) // 4) + "I", blob)
    need(words[0] == 0x07230203 and words[4] == 0, "SPIR-V")
    pos = 5
    bindings, specs, precise, floats, builtins, math_set = [], [], [], [], [], set()
    entry = []
    while pos < len(words):
        count, op = divmod(words[pos], 65536)
        need(count > 0 and pos + count <= len(words), "SPIR-V instruction")
        arg = words[pos + 1 : pos + count]
        if op == 11:
            name = blob[4 * (pos + 2) : 4 * (pos + count)].partition(b"\0")[0]
            if name == b"GLSL.std.450":
                math_set.add(arg[0])
        elif op == 12 and arg[2] in math_set:
            builtins.append(arg[3])
        elif op == 15:
            entry.append((arg[0], blob[4 * (pos + 3) : 4 * (pos + count)].partition(b"\0")[0]))
        elif op == 22:
            floats.append(arg[1])
        elif op == 71:
            if arg[1] == 33:
                bindings.append(arg[2])
            elif arg[1] == 1:
                specs.append(arg[2])
            elif arg[1] == 42:
                precise.append(arg[0])
        pos += count
    need(entry == [(5, b"main")] and sorted(bindings) == [0, 1] and set(specs) == {0}, "interface")
    need(floats == [32] and builtins.count(27) == 1 and precise, "F32 Exp and NoContraction")
    return dict(
        entry="main",
        bindings=sorted(bindings),
        spec_ids=sorted(set(specs)),
        float_widths=floats,
        exp=builtins.count(27),
        no_contraction=len(precise),
    )


def build(a, out):
    _, deploy, _, base = authorities(a)
    sealed(a.backend / "ggml/src/ggml-cpu/ops.cpp", OPS)
    compiler = run_path(RHS / "compile_shader.py")
    lib = compiler["abi"]()
    instance = lib.shaderc_compiler_initialize()
    need(instance, "shaderc init")
    try:
        blob = compiler["compile_spv"](lib, instance, (HERE / "activation.comp").read_bytes(), [])
    finally:
        lib.shaderc_compiler_release(instance)
    reflection = reflect(blob)
    dest = out / "activation.spv"
    dest.write_bytes(blob)
    return dict(
        status="PASS_SWIGLU_SPV_BUILD_ONLY",
        build_inputs=sources(),
        deployment=deploy,
        rhs_build_sha256=OLD_BUILD,
        historical_headers=base["headers"],
        cpu_ops_sha256=OPS,
        shaderc_sha256=compiler["COMPILER_SHA"],
        activation_spv_sha256=digest(dest),
        spirv=reflection,
        physical_dispatches=0,
    )


def sources():
    return {
        name: digest(HERE / name)
        for name in ("activation.comp", "run.py", "grade.py", "protocol.md")
    }


def capture(root):
    sealed(root / "receipt.json", GOLD)
    rec = json.loads((root / "receipt.json").read_bytes())
    need(rec["status"] == "PASS_CPU0_RANK_STAGES_REFERENCE", "CPU family")
    arm = rec["arm"]
    rank = root / "ALIAS/rank"
    verifier = run_path(HERE.parent / "rank_cpu/grade.py")["verify_rank"]
    check = verifier(rank, arm["native"])
    need(arm["rank"] == check, "CPU stage review")
    data = {}
    for name in ("gate-biased", "up-biased", "swiglu"):
        data[name] = (rank / (name + ".f32")).read_bytes()[:11520]
        need(
            hashlib.sha256(data[name]).hexdigest() == check["row_sha256"][name][0], "rank 0 " + name
        )
    data["q8"] = (rank / "down-rank0.q8").read_bytes()
    need(hashlib.sha256(data["q8"]).hexdigest() == check["files_sha256"]["down-rank0.q8"], "CPU Q8")
    return data


def submit(out, name, executable, input_path, modules, rhs, journal, deadline):
    remaining = deadline - time.monotonic()
    need(remaining > 0, "family deadline before " + name)
    folder = out / name
    folder.mkdir()
    layers = folder / "empty-layers"
    layers.mkdir()
    unit = "tesy-igpu-rank-" + out.name + "-" + name
    need(unit.replace("-", "").isalnum() and len(unit) < 165, "unit")
    args = [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--unit",
        unit,
        "-p",
        "MemoryMax=134217728",
        "-p",
        "MemoryHigh=134217728",
        "-p",
        "MemorySwapMax=0",
        "--",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/bin:/bin",
        "LC_ALL=C",
        "VK_DRIVER_FILES=" + str(rhs["BASE"]["ICD"]),
        "VK_LAYER_PATH=" + str(layers),
        "VK_IMPLICIT_LAYER_PATH=" + str(layers),
        "VK_LOADER_LAYERS_DISABLE=~implicit~",
        "MESA_SHADER_CACHE_DISABLE=true",
        "/usr/bin/timeout",
        "-k",
        "1s",
        "9s",
        str(executable),
        str(input_path),
        *map(str, modules),
        str(folder / "actual.bin"),
    ]
    info = {"name": name, "input_sha256": digest(input_path), "scope": unit + ".scope"}
    journal.append(info)
    start = time.monotonic_ns()
    try:
        with (
            (folder / "native.tsv").open("xb") as stdout,
            (folder / "native.stderr").open("xb") as stderr,
        ):
            result = subprocess.run(
                args, stdout=stdout, stderr=stderr, timeout=min(15, remaining), check=False
            )
            info["rc"] = result.returncode
    finally:
        info["child_wall_ns"] = time.monotonic_ns() - start
        ctl = subprocess.run(
            ["systemctl", "--user", "show", unit + ".scope", "-p", "ActiveState", "-p", "SubState"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        info["scope_after"] = ctl.stdout.splitlines()
    need(
        "ActiveState=inactive" in info["scope_after"] and "SubState=dead" in info["scope_after"],
        "scope cleanup",
    )
    need(result.returncode == 0, "dispatch failure " + name)
    info["proof"] = rhs["review"]((folder / "native.tsv").read_text())
    info["module_sha256"] = digest(modules[int(info["proof"]["variant"] == "subgroup")])
    info["files"] = {f: digest(folder / f) for f in ("actual.bin", "native.tsv", "native.stderr")}
    return (folder / "actual.bin").read_bytes()


def run(a, out, row):
    rhs, deploy, old, prior = authorities(a)
    sealed(a.build_dir / "receipt.json", a.build_sha256)
    b = json.loads((a.build_dir / "receipt.json").read_bytes())
    need(
        b["status"] == "PASS_SWIGLU_SPV_BUILD_ONLY"
        and b["deployment"] == deploy
        and b["build_inputs"] == sources()
        and b["rhs_build_sha256"] == OLD_BUILD,
        "activation build provenance",
    )
    spv = a.build_dir / "activation.spv"
    sealed(spv, b["activation_spv_sha256"])
    need(reflect(spv.read_bytes()) == b["spirv"], "SPIR-V readback")
    data = capture(a.rank_dir)
    arith = run_path(HERE.parent / "reference/arithmetic.py")
    need(arith["quantize"](data["swiglu"]) == data["q8"], "pre-dispatch CPU gold")
    row.update(
        cpu_receipt_sha256=GOLD,
        ordered_gate_sha256=ORDER,
        rhs_build_sha256=OLD_BUILD,
        deployment=deploy,
        build_sha256=a.build_sha256,
        jobs=[],
        inputs={k: hashlib.sha256(v).hexdigest() for k, v in data.items()},
    )
    exe = old / "dispatch"
    start = time.monotonic()
    save(out / "before.json", rhs["BASE"]["inventory"]())
    try:
        runs = []
        for idx, chunk in enumerate(grade.segments(data["gate-biased"], data["up-biased"])):
            inp = out / f"input-{idx}.f32"
            inp.write_bytes(chunk)
            runs.append(submit(out, f"a{idx}", exe, inp, [spv, spv], rhs, row["jobs"], start + 90))
            grade.segment_output(runs[-1])
        joined = grade.assemble(runs)
        inp = out / "swiglu.f32"
        inp.write_bytes(joined)
        x4 = submit(
            out,
            "q8",
            exe,
            inp,
            [old / "shared.spv", old / "subgroup.spv"],
            rhs,
            row["jobs"],
            start + 90,
        )
        need(len(x4) == 3312 and x4 != b"\xa5" * 3312, "quantizer output")
        row["result"] = grade.evaluate(data["swiglu"], data["q8"], joined, x4, arith)
        row["swiglu_sha256"] = digest(inp)
        need(
            len(
                {
                    (j["proof"]["pci"], j["proof"]["specialization_id_0"], j["proof"]["variant"])
                    for j in row["jobs"]
                }
            )
            == 1,
            "device changed",
        )
    finally:
        row["family_wall_s"] = time.monotonic() - start
        save(out / "after.json", rhs["BASE"]["inventory"]())
        row["inventory_sha256"] = {f: digest(out / f) for f in ("before.json", "after.json")}
    need(row["family_wall_s"] <= 90, "family wall")
    sealed(exe, prior["files"]["dispatch"])
    row["status"] = "MEASURED_RADV_SWIGLU_AND_DOWN_RHS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    b = commands.add_parser("build")
    b.add_argument("--backend", type=Path, required=True)
    r = commands.add_parser("run")
    r.add_argument("--build-dir", type=Path, required=True)
    r.add_argument("--build-sha256", required=True)
    r.add_argument("--rank-dir", type=Path, required=True)
    for p in (b, r):
        p.add_argument("--rhs-build", type=Path, required=True)
        p.add_argument("--headers", type=Path, required=True)
        p.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    row = {}
    try:
        if args.mode == "build":
            row = build(args, out)
        else:
            run(args, out, row)
    except Exception as exc:
        row.update(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    save(out / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    return int(row["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
