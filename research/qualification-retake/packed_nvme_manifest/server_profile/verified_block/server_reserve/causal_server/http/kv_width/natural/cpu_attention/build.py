"""Build the CPU attention fixture with the sealed row graph and a separate serial control."""

import argparse
import os
import re
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(str(HERE.parent / "family.py"))
G, C, need, sha, save = (F[k] for k in ("G", "C", "need", "sha", "save"))
METHOD = "cf222d414f772c11c5678aa86b00da33bcc48747ffc35f38b8c5de105246d7ec"
NATURAL = "808bc4223c610803a5e7adcf4e5cb687828f60fb5723a12a4829cf99774d94e1"
OPS = "ae3553e5e7773ac4205ac07216e35619230b605a07c2091a3eaf5c6647243cc7"
CASES = {256: 189, 512: 382, 2304: 2062}


def source(gpu):
    # Reuse the allocation, native expression, materialization and F32 exports of part 179.
    text = gpu[: gpu.index("static void stage(")]
    edits = {
        '#include "ggml-cuda.h"': '#include "ggml-cpu.h"',
        "explicit Inputs(int width)": "Inputs(int width, int start, int window)",
        "position(n == 2304 ? 2062 : n - 4)": "position(start)",
        "i <= position+j ? 0": "i <= position+j && (!window || position+j-i < window) ? 0",
        "Serial, Split, WrongMask": "Serial, Block, Split, WrongMask",
        "if (mode == Mode::Serial) {": "if (mode == Mode::Serial || mode == Mode::Block) {",
    }
    for old, new in edits.items():
        need(text.count(old) == 1, "fixture source anchor " + old)
        text = text.replace(old, new)
    return re.sub(r"\bgpu\b", "backend", text) + (HERE / "main.cpp.in").read_text()


def build(a, out, r):
    h, tree = G["tree"](G["REPO"])
    need(h == a.commit and sha(HERE / "protocol.md") == METHOD, "frozen source")
    r.update(commit=h, tree=tree)
    target = G["read"](a.natural / "receipt.json", NATURAL)
    need(
        target["status"] == "FAIL_PRESERVED"
        and target["stage"] == "ON"
        and target["model_starts"] == 3,
        "natural gate",
    )
    ops = a.backend / "ggml/src/ggml-cpu/ops.cpp"
    need(
        sha(ops) == OPS and G["tree"](a.backend)[0] == C["F"]["F"]["OLD"]["C269"],
        "pinned CPU dispatch",
    )
    s = ops.read_text()
    need(
        "const bool use_split_kv_path = !use_ref && (neq1 == 1 && neq3 == 1)" in s
        and "q->type == GGML_TYPE_F32 && nek1 >= 512" in s
        and "ggml_flash_attn_ext_reduce_partials(params, dst, nth, chunk_size);" in s,
        "split-KV source",
    )
    old = G["read"](a.wide / "receipt.json", C["BUILD"])
    physical = G["read"](
        a.natural / "ON/natural-resource.json", target["files"]["ON/natural-resource.json"]
    )
    need(sha(a.wide / "fixture.cpp") == old["program_sha256"], "qualified row expression")
    code = out / "cpu.cpp"
    code.write_text(source((a.wide / "fixture.cpp").read_text()))
    lib = a.backend / "build-c269-cuda/bin"
    compiler = Path("/usr/bin/g++-15")
    need(
        sha(compiler) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a",
        "compiler identity",
    )
    args = [
        compiler,
        "-std=c++17",
        "-O2",
        "-MMD",
        "-MF",
        out / "headers.d",
        "-I",
        a.backend / "ggml/include",
        code,
        "-L",
        lib,
        "-Wl,-rpath," + str(lib),
        "-lggml-cpu",
        "-lggml-base",
        "-o",
        out / "cpu-fixture",
    ]
    env = G["START"]["environment"]([str(lib)])
    G["command"](args, out, out, "compile", env)
    txt = subprocess.check_output(
        ["/usr/bin/ldd", "-r", out / "cpu-fixture"], text=True, env=env, timeout=10
    )
    need("undefined symbol" not in txt and "not found" not in txt, "closure")
    (out / "fixture.ldd").write_text(txt)
    libs = G["START"]["interpret"](txt)
    fleet = G["read"](a.static / "receipt.json", G["STATIC"])["arms"]["C270_PACK"]["closure"]
    providers = {k: dict(file=str(p.resolve(strict=True)), sha256=sha(p)) for k, p in libs.items()}
    need(
        all(fleet[k] == v for k, v in providers.items())
        and {"libggml-cpu.so.0", "libggml-base.so.0"} <= providers.keys(),
        "sealed CPU providers",
    )
    need(
        all(
            physical["pinned"]["startup_dso_sha256"][Path(providers[k]["file"]).name]
            == providers[k]["sha256"]
            for k in ("libggml-cpu.so.0", "libggml-base.so.0")
        ),
        "natural gate CPU and base",
    )
    deps = (out / "headers.d").read_text().replace(chr(92) + "\n", " ").split(":", 1)[1].split()
    headers = {str(Path(k)): sha(Path(k)) for k in deps if Path(k) != code}
    need(any(k.endswith("ggml-cpu.h") for k in headers), "CPU API identity")
    return dict(
        status="GO_CPU_FIXTURE_BUILD",
        elf=sha(out / "cpu-fixture"),
        source_sha256=sha(code),
        providers=providers,
        headers=headers,
        program_179=old["program_sha256"],
        cpu_source=OPS,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("static", "wide", "backend", "natural", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    start = time.monotonic()
    r = dict(status="FAIL_PRESERVED", protocol_sha256=METHOD, natural_sha256=NATURAL)
    try:
        r.update(build(a, out, r))
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    r["wall_s"] = time.monotonic() - start
    r["files"] = {str(k.relative_to(out)): sha(k) for k in sorted(out.rglob("*")) if k.is_file()}
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
