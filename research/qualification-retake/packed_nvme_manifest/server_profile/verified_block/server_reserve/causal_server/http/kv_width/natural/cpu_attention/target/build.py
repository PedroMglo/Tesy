"""Reproduce WIDE and change only the opt-in eligibility of its CPU attention rows."""

import argparse
import os
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(str(HERE.parent / "run.py"))
B, F, G, need, sha, save = (R[k] for k in ("B", "F", "G", "need", "sha", "save"))
METHOD = "32c8dd1355aab2138c52b3304b5f30f52c85b1e3fb28bfca7a262cb518f0c506"
OPERATOR = "1aded710de81d0562f88d7c0dd02da893e04d118b4e7724bc3921d79f7d41fa6"
SWITCH = "TESY_B3_CPU_LONG_ROWS"


def extend(src):
    gate = (
        "        if (arch == LLM_ARCH_OPENAI_MOE && (il == 25 || more_layers) && q->ne[1] == 3 &&"
    )
    need(src.count(gate) == 1 and SWITCH not in src, "unmodified eligibility")
    extra = (
        '        const char *cpu_rows = std::getenv("' + SWITCH + '");\n'
        "        const bool long_cpu = il >= 0 && il < 25 && k->ne[1] >= 512 &&\n"
        '                              cpu_rows && std::strcmp(cpu_rows, "1") == 0;\n'
    )
    return src.replace(
        gate, extra + gate.replace("il == 25 || more_layers", "il == 25 || more_layers || long_cpu")
    )


def build(a, out, r):
    head, tree = G["tree"](G["REPO"])
    need(head == a.commit and sha(HERE / "protocol.md") == METHOD, "frozen source")
    r.update(commit=head, tree=tree)
    op = G["read"](a.operator / "receipt.json", OPERATOR)
    need(
        op["status"] == "GO_CPU_ROW_OPERATOR_ONLY"
        and op["arms"]["1"]["vectors"] == op["arms"]["2"]["vectors"],
        "CPU operator",
    )
    wide = G["read"](a.wide / "receipt.json", F["C"]["BUILD"])
    base = G["read"](a.original / "receipt.json", wide["previous_sha256"])
    current = G["read"](a.static / "receipt.json", G["STATIC"])
    need(wide["status"] == "GO_STATIC_WIDE_KV", "original WIDE")
    old = a.wide / "WIDE"
    lib = G["IMAGE"]
    work = (
        Path(current["arms"]["C281_PACK"]["closure"]["libllama.so.0"]["file"]).parents[1] / "llama"
    )
    inv = G["read"](a.original / "objects.json", base["files"]["objects.json"])

    def objects():
        need(
            len(inv) == 166 and G["digest"]({k: sha(work / k) for k in inv}) == G["OBJECTS"],
            "original 166 objects",
        )

    objects()
    env = dict(PATH="/usr/bin:/bin", LANG="C", LC_ALL="C", TMPDIR=str(out), CUDA_VISIBLE_DEVICES="")
    need(
        G["toolchain"](env) == base["compiler_tools"] and sha(Path("/usr/bin/c++")) == G["DRIVER"],
        "toolchain",
    )
    need(all(sha(Path(k)) == v for k, v in base["link_inputs"].items()), "link inputs")

    def sealed(name):
        p = old / name
        need(sha(p) == wide["files"]["WIDE/" + name], "wide source or recipe")
        return p

    src = sealed("llama-graph.cpp").read_text()
    args = {
        k: G["read"](old / (k + "-argv.json"), wide["files"]["WIDE/" + k + "-argv.json"])
        for k in ("compile", "link")
    }
    headers = G["headers"](sealed("actual.d"), work)
    historic = G["read"](a.original / "BLOCK/headers.json", base["files"]["BLOCK/headers.json"])
    historic.pop(str(a.original / "BLOCK/llama-graph.cpp"))
    need(
        headers == historic | {str(old / "llama-graph.cpp"): sha(old / "llama-graph.cpp")},
        "dependency identities",
    )
    r["images"] = {}
    for name, code in (("CONTROL", src), ("CPU", extend(src))):
        target = out / name
        target.mkdir()
        cpp = target / "llama-graph.cpp"
        cpp.write_text(code)
        for k, cmd in args.items():
            G["command"]([v.replace(str(old), str(target)) for v in cmd], work, target, k, env)
        so = target / lib
        (target / "libllama.so.0").symlink_to(lib)
        need(
            G["headers"](target / "actual.d", work) == historic | {str(cpp): sha(cpp)}
            and G["ABI"](so) == base["original_abi"],
            "unchanged headers or ABI",
        )
        if name == "CONTROL":
            need(
                sha(so) == wide["arms"]["WIDE"]["image_sha256"]
                and sha(target / "llama-graph.cpp.o") == wide["files"]["WIDE/llama-graph.cpp.o"],
                "WIDE reproducibility",
            )
        else:
            need(sha(so) != wide["arms"]["WIDE"]["image_sha256"], "CPU intervention compiled")
        r["images"][name] = dict(
            image=str(so),
            image_sha256=sha(so),
            source_sha256=sha(cpp),
            providers={
                k: G["loader"](current["arms"][k], so, target, k, env)["providers"]
                for k in ("C270_PACK", "C281_PACK")
            },
        )
    objects()
    return "GO_CPU_TARGET_ELF_ONLY"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("operator", "wide", "original", "static", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    t = time.monotonic()
    r = dict(status="FAIL_PRESERVED", protocol_sha256=METHOD, operator_sha256=OPERATOR)
    try:
        r["status"] = build(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r.update(
        wall_s=time.monotonic() - t,
        model_starts=0,
        files={str(k.relative_to(out)): sha(k) for k in sorted(out.rglob("*")) if k.is_file()},
    )
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
