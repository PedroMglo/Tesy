"""Link only after both independent tiny-GPU results are sealed. Never start the client."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
T = run_path(str(HERE.parent / "client/build.py"))
sha, need, pin = T["sha"], T["need"], T["pin"]


def select_tiny(family, review, client_sha, dso_sha, family_sha):
    need(
        family["status"] == "PASS_TINY_HYBRID_GPU_FIXTURE"
        and family["client_sha256"] == client_sha
        and family["dso_sha256"] == dso_sha
        and family["model_sha256"] == T["GOLD"]
        and review["status"] == "REPRODUCED_TINY_HYBRID_GPU_FIXTURE"
        and review["family_sha256"] == family_sha
        and review["launches"] == 3,
        "physical tiny family/review not qualified for this client and DSO",
    )


def prefix():
    cli = (HERE.parent / "client/client.cpp").read_text()
    old = (HERE.parents[1] / "tiny_loader/probe.cpp").read_text()

    def once(text, tag):
        need(text.count(tag) == 1, "observer source boundary " + tag)
        return text.index(tag)

    # Only the tested mmap/madvise, VMA, SET, forwarding and handoff functions enter the build.
    # No source containing a model load, inference call, routing callback or legacy main is taken.
    parts = (
        old[: once(old, "static int tasks()")],
        cli[once(cli, "#undef main\n") + len("#undef main\n") : once(cli, "static bool multiply(")],
        cli[once(cli, "static void handoff(") : once(cli, "static int run(")],
    )
    text = "\n".join(parts)
    need(
        not re.search(r"\b(llama_decode|llama_encode|llama_model_load_from_file|main)\s*\(", text),
        "inference code in observer prefix",
    )
    return text


def build(a, out):
    def load(path, h):
        return json.loads(pin(path / "receipt.json", h).read_bytes())

    tiny = load(a.tiny_client, a.tiny_sha256)
    ds = load(a.dso_build, a.dso_sha256)
    family = load(a.tiny_family, a.tiny_family_sha256)
    rev = load(a.tiny_review, a.tiny_review_sha256)
    select_tiny(family, rev, a.tiny_sha256, a.dso_sha256, a.tiny_family_sha256)
    need(
        tiny["status"] == "PASS_TINY_HYBRID_CLIENT_BUILD"
        and tiny["variant"] == "cuda"
        and ds["status"] == "PASS_IK_SM89_LINK_ONLY"
        and tiny["dso_build_sha256"] == a.dso_sha256,
        "qualified tiny build/DSOs",
    )
    src = a.source.resolve()
    settings = run_path(str(HERE.parent / "configure.py"))
    settings["pin"](src)
    for name in ("client.cpp", "hooks.hpp", "copy.cpp", "rank_view.hpp"):
        pin(HERE.parent / "client" / name, tiny["sources"][name])
    for rel in ("tiny_loader/probe.cpp", "cpu_numeric/vma/inspect.hpp"):
        pin(HERE.parents[1] / rel, tiny["sources"][rel])
    pin(T["TOOLKIT"] / "cuda_runtime_api.h", tiny["runtime_header_sha256"])
    (out / "observe_prefix.hpp").write_text(prefix())
    obj = (a.dso_build / "objects").resolve()
    for rel, h in tiny["libraries"].items():
        need(ds["libraries"]["objects/" + rel] == h, "ik library")
        pin(obj / rel, h)
    # Reuse the sealed driver's ABI/frontend/toolchain and its exact rpath-link search.
    compiler = Path(tiny["compile_argv"][0])
    pin(compiler.resolve(), tiny["compiler_sha256"])
    cli = HERE.parent / "client"
    exe = out / "capacity-client"
    cmd = [
        compiler,
        "-std=c++17",
        "-O1",
        "-pthread",
        "-rdynamic",
        "-fPIC",
        "-pie",
        "-fno-plt",
        *(f"-I{src / x}" for x in ("include", "ggml/include", "ggml/src")),
        f"-I{T['TOOLKIT']}",
        f"-I{out}",
        f"-I{cli}",
        HERE / "capacity.cpp",
        cli / "copy.cpp",
        *(obj / x for x in T["LIBS"]),
        "-ldl",
        "-o",
        exe,
        *[v for v in tiny["compile_argv"] if v.startswith("-Wl,-rpath-link,")],
    ]
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=60)
    symbols = subprocess.check_output(["/usr/bin/nm", "-Du", exe], text=True)
    need(
        not re.search(r"\b(llama_decode|llama_encode)(?:@|$)", symbols, re.M),
        "unexpected forward dependency",
    )
    paths, closure = T["device_closure"](exe, obj, ds, SimpleNamespace(env49_map=a.env49_map))
    need(paths == tiny["explicit_search"] and closure == tiny["closure"], "tiny/capacity closure")
    sources = {
        k: sha(HERE / k)
        for k in ("capacity.cpp", "build.py", "inventory.py", "grade.py", "protocol.md")
    }
    sources.update(
        {
            f"client/{k}": sha(cli / k)
            for k in ("copy.cpp", "hooks.hpp", "client.cpp", "rank_view.hpp")
        }
    )
    sources.update(
        {
            k: sha(HERE.parents[1] / k)
            for k in ("tiny_loader/probe.cpp", "cpu_numeric/vma/inspect.hpp")
        }
    )
    sources["observe_prefix.hpp"] = sha(out / "observe_prefix.hpp")
    git = ["git", "-C", str(HERE), "rev-parse"]
    return dict(
        status="PASS_IK_CAPACITY_CLIENT_BUILD",
        binary=exe.name,
        binary_sha256=sha(exe),
        libraries=tiny["libraries"],
        closure=closure,
        explicit_search=paths,
        native_search=os.pathsep.join(paths),
        native_search_sha256=tiny["native_search_sha256"],
        sources=sources,
        ik_commit=tiny["ik_commit"],
        commit=subprocess.check_output([*git, "HEAD"], text=True).strip(),
        tree=subprocess.check_output([*git, "HEAD^{tree}"], text=True).strip(),
        compile_argv=list(map(str, cmd)),
        compiler_sha256=tiny["compiler_sha256"],
        dso_build_sha256=a.dso_sha256,
        tiny_client_sha256=a.tiny_sha256,
        tiny_family_sha256=a.tiny_family_sha256,
        tiny_review_sha256=a.tiny_review_sha256,
        model_loads=0,
        forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "source",
        "tiny-client",
        "tiny-family",
        "tiny-review",
        "dso-build",
        "env49-map",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    for key in ("tiny-sha256", "tiny-family-sha256", "tiny-review-sha256", "dso-sha256"):
        p.add_argument("--" + key, required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        r = build(a, out)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"])
    return r["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
