"""Reuse the frozen primary allocator, exact binaries and SPIR-V for two DOWN reads."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PRIMARY = HERE.parent / "primary_import"
P = run_path(PRIMARY / "build.py")
B, BASE, need, save, sha = (P[k] for k in ("B", "BASE", "need", "save", "sha"))
PROTO = "c705cf2644bfbea4914ac3896ba51f45fbacc098955fbda59aa35ea3619fa5f0"
PREVIOUS = "ef67fa3aee5f5f0ca8cd279e9eb3823cc270501e1a341922324a64c13c2af89e"


def inputs():
    need(sha(HERE / "protocol.md") == PROTO, "rank down protocol")
    return dict(
        primary=P["inputs"](),
        sources={n: sha(HERE / n) for n in ("build.py", "run.py", "protocol.md")},
    )


def sources(out):
    P["generate"](out)
    replace = B["replace"]
    # Limit SETs, authentication and dispatches to the two actual DOWN slot views.
    src = (PRIMARY / "primary.inc").read_text()
    loop = "for(int r=0;r<2;r++)for(int k=0;k<3;k++)"
    need(src.count(loop) == 2, "two role loops")
    src = src.replace(loop, "for(int r=0,k=1;r<2;r++)")
    (out / "primary.inc").write_text(replace(src, "(role==0 || role==2)", "role==1"))
    src = (out / "projection.inc").read_text()
    start = src.index("    cache.select(0);")
    end = src.index("    vkDestroyPipeline(p.dev,pipeline", start)
    (out / "projection.inc").write_text(
        src[:start] + "    cache.select(0);emit(1,args[7]);cache.release_after_fence();\n"
        "    cache.select(1);emit(1,args[8]);cache.release_after_fence();cache.cleanup();\n"
        + src[end:]
    )
    f = out / "dispatch.cpp"
    f.write_text(
        replace(
            replace(f.read_text(), "argc==10", "argc==9"),
            "PASS_PRIMARY_CPU_IMPORT",
            "PASS_RANK_DOWN",
        )
    )


def build(a, out):
    import json

    previous = json.loads((a.primary_build / "receipt.json").read_bytes())
    need(sha(a.primary_build / "receipt.json") == PREVIOUS, "frozen primary build")
    current = P["inputs"]()
    prior = previous["inputs"]
    for seals in (prior, current):
        revision = seals["predecessor"]["stock_source"]["deployment"]["deployment"]
        del revision["commit"], revision["tree"]
    need(current == prior, "same primary source and providers")
    inc = a.backend / "ggml/include"
    libs = P["libs"](a.backend)
    need(all(sha(inc / n) == v for n, v in previous["cpu_headers"].items()), "GGML headers")
    need(
        all(sha(a.headers / "vulkan" / n) == v for n, v in B["HEADERS"].items()), "Khronos headers"
    )
    sources(out)
    for n in ("gate.spv", "subgroup.spv", "shared.spv"):
        need(sha(a.primary_build / n) == previous["files"][n], "frozen shader " + n)
        shutil.copyfile(a.primary_build / n, out / n)
    command = [
        str(BASE["CXX"]),
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-missing-field-initializers",
        *[f'-D{k.upper()}_DSO="{f}"' for k, f in libs.items()],
        "-I",
        str(inc),
        "-I",
        str(a.headers),
        "-I",
        str(out),
        "-I",
        str(P["P"]["STOCK"]),
        str(out / "dispatch.cpp"),
        str(libs["cpu"]),
        str(libs["base"]),
        str(BASE["LOADER"]),
        str(B["CRYPTO"]),
        "-Wl,-rpath," + str(libs["cpu"].parent),
        "-o",
        str(out / "rank"),
    ]
    with (out / "build.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=True)
    return dict(
        status="PASS_RANK_DOWN_BUILD",
        primary_build=PREVIOUS,
        inputs=inputs(),
        providers={k: str(v) for k, v in libs.items()},
        files={f.name: sha(f) for f in sorted(out.iterdir()) if f.is_file()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("backend", "headers", "primary-build", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        row = build(a, out)
    except Exception as exc:
        row = dict(status="FAIL_PRESERVED", reason=str(exc))
    save(out / "receipt.json", row)
    print(row["status"], row.get("reason", ""))
    raise SystemExit(int(row["status"] == "FAIL_PRESERVED"))
