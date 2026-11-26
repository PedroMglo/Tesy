"""Relink one GGML graph translation unit and retain the exact published observer ELF."""

import argparse
import hashlib
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE.parent / "operands.py"))
OLD = run_path(str(D["ATT"] / "full_graph/build.py"))
F = run_path(str(D["ATT"] / "full_graph/pair.py"))
P, S, N, Q, need, read, sha, save = (
    OLD[k] for k in ("P", "S", "N", "Q", "need", "read", "sha", "save")
)
METHOD = "1773557f5bb598126ff533e704858c96052bd788af8788f77ab7f40b62405a19"
PREVIOUS = "8840e511e92f6124f6ffd619d5495c46f3419e99f600648c69dfd641c261c0af"
RECIPES = {
    "graph-compile": "b5fb3d94537e056c08cc82f5612c713b4219183ec9c0e7c747e597cdc59d55c4",
    "graph-link": "26f1fa317200e4029ff4c178ae731042768d1a863eeff1239e4e4117bc604f95",
}
FLAG = "TESY_B3_GPU_REPAIR"


def graph(source):
    once = OLD["M"]["once"]
    needle = "    experts = build_lora_mm_id(down_exps, cur, ids_gemm, down_exps_s, logical_ids);"
    modified = once(source, needle, (HERE / "down.inc").read_text() + needle)
    start = (
        "        if (arch == LLM_ARCH_OPENAI_MOE && il == 25 && q->ne[1] == 3 &&\n"
        "                q->ne[3] == 1 && k->ne[1] == 256 && rows_mode && "
        'std::strcmp(rows_mode, "1") == 0) {'
    )
    selection = """        const char *gpu_repair = std::getenv("TESY_B3_GPU_REPAIR");
        const bool more_layers = il > 25 && il <= 35 && gpu_repair &&
                                 std::strcmp(gpu_repair, "CUDA") == 0;
        if (arch == LLM_ARCH_OPENAI_MOE && (il == 25 || more_layers) && q->ne[1] == 3 &&
                rows_mode && std::strcmp(rows_mode, "1") == 0) {
            GGML_ASSERT(q->ne[3] == 1 && k->ne[1] > 0 && (il != 25 || k->ne[1] == 256));
            std::fprintf(stderr, "tesy_b3_built attention %d %lld\\n", il, (long long) k->ne[1]);"""
    modified = once(modified, start, selection)
    modified = once(
        modified,
        "kq_mask->ne[0] == 256 && kq_mask->ne[1] == 3",
        "kq_mask->ne[0] == k->ne[1] && kq_mask->ne[1] == 3",
    )
    return once(
        modified, "ggml_view_2d(ctx0, kq_mask, 256, 1,", "ggml_view_2d(ctx0, kq_mask, k->ne[1], 1,"
    )


def build(a, out):
    git = P["prepare"].git
    need(
        sha(HERE / "protocol.md") == METHOD
        and git(HERE, "rev-parse", "HEAD") == a.commit
        and not git(HERE, "status", "--porcelain")
        and sha(a.parent / "receipt.json") == PREVIOUS,
        "method and parent",
    )
    prior = read(a.parent / "receipt.json")
    need(
        prior["status"] == "GO_INTEGRATED_ATTENTION_PAIR"
        and sha(a.parent / "llama-graph.cpp") == prior["graph_source_sha256"]
        and sha(a.parent / "b3-numeric") == prior["elf_sha256"]
        and sha(a.parent / "boundary.cpp") == prior["client_source_sha256"]
        and sha(a.parent / "libllama.so.0.0.9884") == prior["image_sha256"],
        "prior numerical implementation",
    )
    pf = S["G"]["probes"].load(Q / "phase_fd/integrated/build.py", "down_link")
    stock = S["G"]["probes"].load(Q / "stock_prefault_build/build.py", "down_abi")
    backend = a.backend.resolve(strict=True)
    directory = backend / "build-c269-cuda"
    need(
        git(backend, "rev-parse", "HEAD") == pf.WORKER
        and not git(backend, "status", "--porcelain")
        and sha(Path(pf.CXX)) == stock.GCC == prior["compiler_sha256"],
        "pin and compiler",
    )
    tokens = shlex.split(
        pf.cmd("ninja", "-C", directory, "-t", "commands", "bin/" + pf.IMAGE).splitlines()[-1]
    )
    originals = {
        t: sha(directory / t)
        for t in tokens
        if t.endswith(".o") or (not t.startswith("-") and ".so" in t and t != "bin/" + pf.IMAGE)
    }
    need(
        len(originals) == 171
        and pf.stamp(originals) == pf.INPUTS == prior["link_inputs_sha256"]
        and pf.stamp(tokens) == pf.LINK,
        "pinned link inputs",
    )
    source = graph((a.parent / "llama-graph.cpp").read_text())
    (out / "llama-graph.cpp").write_text(source)
    env = pf.ENV | {"TMPDIR": str(out)}
    for tag, digest in RECIPES.items():
        recipe = a.parent / (tag + ".json")
        need(sha(recipe) == digest, "frozen recipe")
        cmd = [t.replace(str(a.parent), str(out)) for t in read(recipe)]
        OLD["native"](
            cmd, directory, env, out / (tag + ".log"), 150 if tag == "graph-compile" else 60
        )
    library = out / pf.IMAGE
    need(
        sha(library) != prior["image_sha256"]
        and stock.abi(library)["dynamic"] == stock.abi(a.parent / pf.IMAGE)["dynamic"]
        and all(sha(directory / t) == v for t, v in originals.items()),
        "ABI and original inputs after relink",
    )
    (out / pf.SONAME).symlink_to(library.name)
    exe = out / "b3-numeric"
    shutil.copy2(a.parent / "b3-numeric", exe)
    need(sha(exe) == prior["elf_sha256"], "observer ELF")
    auth = OLD["Authority"](a.static, out, prior["elf_sha256"], sha(library))
    env = P["SC"]["OLD"]["environment"](auth.search.split(os.pathsep))
    closure = subprocess.check_output(["/usr/bin/ldd", "-r", exe], env=env, text=True, timeout=20)
    (out / "ldd.txt").write_text(closure)
    need(
        "not found" not in closure
        and "undefined symbol" not in closure
        and {k: str(v.resolve()) for k, v in P["SC"]["OLD"]["interpret"](closure).items()}
        == {k: v["file"] for k, v in auth.verified["closure"].items()},
        "startup closure",
    )
    for mode in ("BASE", "D25", "CUDA"):
        child = subprocess.run(
            [exe, "--self-test"],
            env=env
            | {"CUDA_VISIBLE_DEVICES": "", P["B"]["ON"]: "1", OLD["M"]["OPTION"]: "1", FLAG: mode},
            capture_output=True,
            timeout=15,
            check=True,
        )
        (out / ("self-" + mode + ".log")).write_bytes(child.stdout + child.stderr)
        need(child.stdout == b"PASS_B3_NUMERIC_ROW_PLAN\n", "observer without a model")
    return dict(
        status="GO_TARGET_FFN_FAMILY",
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        protocol_sha256=METHOD,
        parent_sha256=PREVIOUS,
        elf_sha256=sha(exe),
        image_sha256=sha(library),
        original_source_sha256=prior["graph_source_sha256"],
        graph_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        current_providers=auth.verified["closure"],
        compiler_sha256=stock.GCC,
        link_inputs_sha256=pf.INPUTS,
        method_sources={k: sha(HERE / k) for k in ("build.py", "down.inc")},
        reused_objects=165,
        model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("new-output-dir", "backend", "parent", "static"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    start = time.monotonic()
    try:
        r = build(a, out)
        need(
            time.monotonic() - start < 300
            and sum(p.stat().st_size for p in out.iterdir() if p.is_file()) < 150 << 20,
            "build budget",
        )
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}", model_starts=0)
    r["wall_s"] = time.monotonic() - start
    save(out / "receipt.json", r)
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
