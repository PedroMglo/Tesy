"""Bind the tested CUDA bank reader to the original callback-selectable 120B client."""

import argparse
import json
import os
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
HYBRID = HERE.parents[2]
SMALL = run_path(str(HERE.parent / "tiny_graph/build.py"))
CB = run_path(str(HYBRID / "full_parity/callback/build.py"))
PAR = CB["ORIGINAL"]
once, need, sha, git = PAR["once"], SMALL["need"], SMALL["sha"], SMALL["git"]
HIST = "133315b9095ff5944b3017dc7b979287f7a3dcd35b485b59b86316c92b224b23"


def render(src, prefix):
    prefix = once(
        prefix,
        'extern "C" void ggml_backend_tensor_set(',
        '#include "graph_input.hpp"\nextern "C" void ggml_backend_tensor_set(',
    )
    anchor = "    real(b,t,src,off,n);"
    prefix = once(
        prefix,
        anchor,
        "    if (graph_input::active &&\n"
        "        graph_input::active->send(b,t,src,off,n,real)) return;\n" + anchor,
    )
    anchor = "    handoff(false,'E');"
    src = once(
        src,
        anchor,
        """    const char *source_choice = std::getenv("TESY_C110_SOURCE");
    must(source_choice, "missing bank input mode");
    graph_input::Session session(path.c_str(), source_choice, {36, 648155136, 16, true, false});
    std::printf("BANK_MODE %s\\n", source_choice);
"""
        + anchor,
    )
    anchor = "    census(model,plan);"
    src = once(
        src,
        anchor,
        anchor
        + """
    for (int i=0; i<36; ++i) for (const char *role : {"gate","up","down"}) {
        const std::string name = "blk."+std::to_string(i)+".ffn_"+role+"_exps.weight";
        session.add(i,role,"weight",llama_get_model_tensor(model,name.c_str()));
    }""",
    )
    src = once(src, "    llama_free(ctx);", "    session.finish();\n    llama_free(ctx);")
    return src, prefix


def build(a, out, r):
    need(
        git(HERE, "rev-parse", "HEAD") == a.commit and not git(HERE, "status", "--porcelain"),
        "unfrozen checkout",
    )
    need(
        git(a.source, "rev-parse", "HEAD") == SMALL["IK"]
        and not git(a.source, "status", "--porcelain"),
        "ik pin",
    )
    need(
        sha(a.client / "receipt.json") == HIST and sha(a.ids) == PAR["IDS"],
        "original build or input",
    )
    b = json.loads((a.client / "receipt.json").read_bytes())
    need(sha(a.client / "callback-client") == b["binary_sha256"], "reference ELF")
    cli = HYBRID / "client"
    parts = PAR["render"](
        (HYBRID / "capacity/capacity.cpp").read_text(),
        (cli / "client.cpp").read_text(),
        (cli / "rank_view.hpp").read_text(),
        PAR["PRE"]["prefix"](),
    )
    ids = struct.unpack("<17i", a.ids.read_bytes())
    parts["ids_expected.hpp"] = (
        "static constexpr std::array<llama_token,17> expected_ids = {"
        + ",".join(map(str, ids))
        + "};\n"
    )
    for name, content in parts.items():
        need(
            content == (a.client / "control" / name).read_text(), "changed original source " + name
        )
    src = CB["render"](parts["parity.cpp"])
    need(
        src == (a.client / "parity.cpp").read_text()
        and sha(a.client / "parity.cpp") == b["source_sha256"],
        "reference callback client source",
    )
    parts["parity.cpp"], parts["observe_prefix.hpp"] = render(src, parts["observe_prefix.hpp"])
    for name, content in parts.items():
        (out / name).write_text(content)
    obj = a.dso.resolve() / "objects"
    need(sha(a.dso / "receipt.json") == b["dso_sha256"], "DSO build")
    for file, digest in b["libraries"].items():
        need(sha(obj / file) == digest, "DSO drift")
    compiler = Path("/usr/bin/g++-15")
    need(sha(compiler) == b["compiler_sha256"], "compiler")
    exe = out / "c110-bank-input"
    cmd = [
        str(compiler),
        "-std=c++17",
        "-O1",
        "-pthread",
        "-rdynamic",
        "-fPIC",
        "-pie",
        "-fno-plt",
        *(f"-I{a.source / p}" for p in ("include", "ggml/include", "ggml/src")),
        "-I/usr/local/cuda-13.3/include",
        *(f"-I{p}" for p in (out, HYBRID / "full_parity", cli, HERE.parent / "tiny_graph")),
        str(out / "parity.cpp"),
        str(cli / "copy.cpp"),
        str(obj / "src/libllama.so"),
        str(obj / "ggml/src/libggml.so"),
        "-ldl",
        "-o",
        str(exe),
        *(
            "-Wl,-rpath-link," + str(p)
            for p in (obj / "ggml/src", "/usr/lib64", "/usr/local/cuda-13.3/lib64")
        ),
    ]
    r.update(
        commit=a.commit,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        ik=SMALL["IK"],
        sources={
            p.name: sha(p)
            for p in [
                *(out / n for n in parts),
                HERE / "build.py",
                HERE.parent / "bank_input.hpp",
                HERE.parent / "tiny_graph/graph_input.hpp",
            ]
        },
        original_build=HIST,
        compiler_sha256=b["compiler_sha256"],
        compile_argv=cmd,
    )
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=60)
    r.update(status="PASS_C110_INPUT_BUILD", binary_sha256=sha(exe))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "client", "dso", "ids", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0)
    try:
        build(a, out, r)
    except Exception as exc:
        r["reason"] = f"{type(exc).__name__}: {exc}"
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
