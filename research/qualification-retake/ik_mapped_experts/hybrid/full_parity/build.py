"""Link the 16+teacher witness from the already sealed capacity and tiny clients."""

import argparse
import json
import struct
import subprocess
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CAP = HERE.parent / "capacity"
CLI = HERE.parent / "client"
PRE = run_path(str(CAP / "build.py"))
T = PRE["T"]
sha, need, pin = T["sha"], T["need"], T["pin"]
IDS = "378eeb5ae41c80e16df38faad214c82e138727d2ddc1723a44f09c29c6e0f75c"


def once(text, old, new):
    need(text.count(old) == 1, "expected exactly one source anchor " + old[:48])
    return text.replace(old, new)


def render(original, tiny, rank, observer):
    start = tiny.index("static bool multiply(")
    graph = tiny[start : tiny.index("static void output(", start)]
    graph = once(graph, "tiny_rank::router(t->name)", "real_router(t->name)")
    graph = once(graph, "observe::phase == 3 ? 32 : 1", "rank_width(node->name)")
    graph = once(
        graph, 'std::printf("NODE ', 'if (!mm) compare_bias(t, w, arg);\n    std::printf("NODE '
    )
    start = original.index('extern "C" ggml_status ggml_backend_graph_compute_async(')
    stop = original.index("static void census(", start)
    native = original[:start] + original[stop:]
    native = once(
        native,
        "static void bias_instances(",
        "#include <map>\nstatic std::map<std::string, const ggml_tensor *> host_biases;\n"
        "static void bias_instances(",
    )
    native = once(
        native,
        'std::printf("BIAS_INSTANCE ',
        'if (host) must(host_biases.emplace(name,tensor).second,"duplicate host bias");\n'
        '        std::printf("BIAS_INSTANCE ',
    )
    native = once(
        native, "static int probe(", '#include "parity.hpp"\n' + graph + "\nstatic int probe("
    )
    native = once(
        native,
        'must(argc==4,"capacity-client ORIGINAL.GGUF PLAN.TSV NEW_NATIVE_DIR");',
        """must(argc==6,"parity-client BANK288|BANK161 MODEL PLAN IDS NATIVE");
    const std::string mode(argv[1]);
    must(mode=="BANK288" || mode=="BANK161","mode");
    auto ids=read_input(argv[4]);
    // Adapt the remaining capacity routine's argv, sharing its exact paths and identity checks.
    char *inputs[]={argv[0],argv[2],argv[3],argv[5]};
    argv=inputs;""",
    )
    native = once(
        native,
        "p.moe_cache_size=3644ULL<<20;",
        'p.moe_cache_size=(mode=="BANK288" ? 3644ULL : 2048ULL)<<20;',
    )
    native = once(native, "p.cb_eval=nullptr;", "p.cb_eval=callback; p.logits_all=false;")
    native = once(
        native,
        "observe::phase=5;",
        "const int outcome=supplied_cuts(ctx,dir,ids);\n    observe::phase=5;",
    )
    native = once(
        native, "handoff(false,'F');", "if (outcome) return outcome;\n    handoff(false,'F');"
    )
    native = once(
        native, "STATUS COMPLETED_IK_CAPACITY_ZERO_FORWARD", "STATUS COMPLETED_IK_GPU_BANK_CUTS"
    )
    return {
        "parity.cpp": native,
        "parity_rank_view.hpp": once(
            rank, "(width != 1 && width != 32)", "(width != 1 && width != 16)"
        ),
        "observe_prefix.hpp": once(
            observer, '#include "rank_view.hpp"', '#include "parity_rank_view.hpp"'
        ),
    }


def build(a, out):
    original = json.loads(pin(a.capacity_build / "receipt.json", a.capacity_sha256).read_bytes())
    ds = json.loads(pin(a.dso_build / "receipt.json", original["dso_build_sha256"]).read_bytes())
    need(
        original["status"] == "PASS_IK_CAPACITY_CLIENT_BUILD"
        and ds["status"] == "PASS_IK_SM89_LINK_ONLY",
        "unqualified predecessor",
    )
    run_path(str(HERE.parent / "configure.py"))["pin"](a.source)
    for key, path in (
        ("client/client.cpp", CLI / "client.cpp"),
        ("client/rank_view.hpp", CLI / "rank_view.hpp"),
        ("client/copy.cpp", CLI / "copy.cpp"),
        ("client/hooks.hpp", CLI / "hooks.hpp"),
        ("capacity.cpp", CAP / "capacity.cpp"),
        ("observe_prefix.hpp", a.capacity_build / "observe_prefix.hpp"),
        ("cpu_numeric/vma/inspect.hpp", HERE.parents[1] / "cpu_numeric/vma/inspect.hpp"),
    ):
        pin(path, original["sources"][key])
    data = pin(a.ids, IDS).read_bytes()
    ids = struct.unpack("<17i", data)
    need(ids[-1] == 976 and all(0 <= i < 201088 for i in ids), "C110 input")
    parts = render(
        (CAP / "capacity.cpp").read_text(),
        (CLI / "client.cpp").read_text(),
        (CLI / "rank_view.hpp").read_text(),
        (a.capacity_build / "observe_prefix.hpp").read_text(),
    )
    parts["ids_expected.hpp"] = (
        "static constexpr std::array<llama_token,17> expected_ids = {"
        + ",".join(map(str, ids))
        + "};\n"
    )
    for name, text in parts.items():
        (out / name).write_text(text)
    obj = (a.dso_build / "objects").resolve()
    compiler = Path(original["compile_argv"][0])
    pin(compiler.resolve(), original["compiler_sha256"])
    for rel, digest in original["libraries"].items():
        need(ds["libraries"]["objects/" + rel] == digest, "DSO authority")
        pin(obj / rel, digest)
    exe = out / "parity-client"
    cmd = [
        compiler,
        "-std=c++17",
        "-O1",
        "-pthread",
        "-rdynamic",
        "-fPIC",
        "-pie",
        "-fno-plt",
        *(f"-I{a.source / x}" for x in ("include", "ggml/include", "ggml/src")),
        f"-I{T['TOOLKIT']}",
        f"-I{out}",
        f"-I{HERE}",
        f"-I{CLI}",
        out / "parity.cpp",
        CLI / "copy.cpp",
        *(obj / rel for rel in T["LIBS"]),
        "-ldl",
        "-o",
        exe,
        *[v for v in original["compile_argv"] if v.startswith("-Wl,-rpath-link,")],
    ]
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    search, closure = T["device_closure"](exe, obj, ds, SimpleNamespace(env49_map=a.env49_map))
    need(search == original["explicit_search"] and closure == original["closure"], "loader closure")
    sources = {
        k: sha(HERE / k)
        for k in ("protocol.md", "parity.hpp", "build.py", "grade.py", "contrast.py")
    }
    sources.update({k: sha(out / k) for k in parts})
    return dict(
        status="PASS_IK_FULL_PARITY_CLIENT_BUILD",
        binary=exe.name,
        binary_sha256=sha(exe),
        capacity_client_sha256=a.capacity_sha256,
        dso_build_sha256=original["dso_build_sha256"],
        libraries=original["libraries"],
        closure=closure,
        explicit_search=search,
        native_search=original["native_search"],
        native_search_sha256=original["native_search_sha256"],
        tiny_family_sha256=original["tiny_family_sha256"],
        tiny_review_sha256=original["tiny_review_sha256"],
        ik_commit=original["ik_commit"],
        commit=subprocess.check_output(
            ["git", "-C", str(HERE), "rev-parse", "HEAD"], text=True
        ).strip(),
        tree=subprocess.check_output(
            ["git", "-C", str(HERE), "rev-parse", "HEAD^{tree}"], text=True
        ).strip(),
        inputs_sha256=IDS,
        sources=sources,
        compile_argv=list(map(str, cmd)),
        compiler_sha256=original["compiler_sha256"],
        model_loads=0,
        forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "dso-build", "capacity-build", "env49-map", "ids", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--capacity-sha256", required=True)
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    try:
        r = build(a, out)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    (out / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"])
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
