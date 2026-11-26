"""Compile the qualified C110 client with deferred service recording and native phase clocks."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE.parent / "build.py"))
need, sha, once, git = (B[k] for k in ("need", "sha", "once", "git"))
PARENT_BUILD = "12ce2e8494cf04529e2136c0861a3962538eb3870507c6b1e1376cbab5825216"
PARENT_ELF = "d11e65584a66c3bf8815a331d8027c63799249b2cee43d811e113d893c762cb2"


def replace_block(source, first, following, change):
    need(source.count(first) == source.count(following) == 1, "changed source block")
    start = source.index(first)
    end = source.index(following, start + len(first))
    return source[:start] + change + source[end:]


def render(sources):
    src = sources["parity.cpp"]
    src = once(
        src,
        "    handoff(false,'E');",
        "    handoff(false,'E');\n    input_price::cold_file(fd,id.bytes);",
    )
    src = once(
        src,
        '    std::printf("CB_EVAL',
        '    must(!use_callback, "cost requires OFF");\n    std::printf("CB_EVAL',
    )
    src = replace_block(
        src,
        "    auto rc = real(b,g);",
        "\n}\n\nstatic std::string rank_ids",
        "    return real(b,g);",
    )
    src = once(
        src,
        "    session.finish();",
        "    const auto cleanup_start=input_price::Clock::now();\n    session.finish();",
    )
    src = once(
        src,
        "llama_backend_free();",
        "llama_backend_free();\n    input_price::cleanup_ns=input_price::ns_since(cleanup_start);",
    )
    src = once(
        src,
        "    if (outcome) return outcome;",
        "    if (outcome) return outcome;\n    input_price::save(dir);",
    )
    prefix = once(
        sources["observe_prefix.hpp"],
        '#include "graph_input.hpp"',
        '#include "price.hpp"\n#include "graph_input.hpp"',
    )
    prefix = once(
        prefix,
        "        if (!observe::phase) return;",
        "        if (!observe::phase || observe::phase == 3 || observe::phase == 4) return;",
    )
    cuts = once(
        sources["parity.hpp"],
        "        must(llama_decode",
        "        const auto start=input_price::Clock::now();\n        must(llama_decode",
    )
    cuts = once(
        cuts,
        "        llama_synchronize(ctx);",
        "        llama_synchronize(ctx);\n"
        "        input_price::forward_ns[prefill ? 0 : 1]=input_price::ns_since(start);",
    )
    graph = sources["graph_input.hpp"]
    graph = replace_block(graph, '        std::printf("BANK_GET', "\n    }\n    bool fence", "")
    graph = replace_block(
        graph,
        '        std::printf("BANK_FENCE',
        "        ids = nullptr;",
        "        ++generation;\n        input_price::record_ranks(observe::phase,ids,id_count);\n",
    )
    graph = replace_block(
        graph,
        "        auto file = observe::file_offset(src,n);",
        "        input->send(",
        "        const auto file = selected->offset + int64_t(ptr-selected->address);\n",
    )
    graph = replace_block(
        graph,
        '            std::printf("BANK_SOURCE',
        "            real(b,t,effective,off,n);",
        "            input_price::record_set(observe::phase,generation,selected->layer,"
        "t->name,file,off,n);\n",
    )
    return sources | {
        "parity.cpp": src,
        "observe_prefix.hpp": prefix,
        "parity.hpp": cuts,
        "graph_input.hpp": graph,
    }


def build(a, r):
    head = git(HERE, "rev-parse", "HEAD")
    need(head == a.commit and not git(HERE, "status", "--porcelain"), "unfrozen checkout")
    need(
        git(a.source, "rev-parse", "HEAD") == B["SMALL"]["IK"]
        and not git(a.source, "status", "--porcelain"),
        "ik pin",
    )
    need(sha(a.parent / "receipt.json") == PARENT_BUILD, "input build receipt")
    old = json.loads((a.parent / "receipt.json").read_bytes())
    need(
        sha(a.parent / "c110-bank-input") == old["binary_sha256"] == PARENT_ELF, "qualified binary"
    )
    hybrid = B["HYBRID"]
    parent = HERE.parents[1]
    selected = {
        k: a.parent / k
        for k in ("parity.cpp", "observe_prefix.hpp", "ids_expected.hpp", "parity_rank_view.hpp")
    }
    selected["graph_input.hpp"] = parent / "tiny_graph/graph_input.hpp"
    need(all(sha(p) == old["sources"][k] for k, p in selected.items()), "qualified sources")
    need(sha(parent / "bank_input.hpp") == old["sources"]["bank_input.hpp"], "qualified reader")
    selected["parity.hpp"] = hybrid / "full_parity/parity.hpp"
    # This header was included directly from the same checked-out tree by the qualified build.
    header = subprocess.check_output(
        [
            "git",
            "-C",
            HERE,
            "show",
            old["commit"]
            + ":"
            + str(
                selected["parity.hpp"].relative_to(Path(git(HERE, "rev-parse", "--show-toplevel")))
            ),
        ]
    )
    need(header == selected["parity.hpp"].read_bytes(), "qualified forward cuts")
    sources = render({k: p.read_text() for k, p in selected.items()})
    out = a.new_output_dir.resolve()
    for k, content in sources.items():
        (out / k).write_text(content)
    cmd = old["compile_argv"].copy()
    need(sha(Path(cmd[0])) == old["compiler_sha256"], "compiler")
    # Rebind the frozen command to the new sources. All DSOs and compiler flags are shared.
    qualified = str(Path(cmd[cmd.index("-o") + 1]).parent)
    for original, new in (
        ("-I" + qualified, "-I" + str(out)),
        (qualified + "/parity.cpp", str(out / "parity.cpp")),
        (qualified + "/c110-bank-input", str(out / "c110-price")),
    ):
        need(cmd.count(original) == 1, "unexpected compiler input")
        cmd[cmd.index(original)] = new
    cmd.remove(str(hybrid / "client/copy.cpp"))
    cmd.insert(cmd.index("-I" + str(out)) + 1, "-I" + str(HERE))
    r.update(
        commit=head,
        tree=git(HERE, "rev-parse", "HEAD^{tree}"),
        parent_build=PARENT_BUILD,
        compile_argv=cmd,
        original_sources={k: sha(p) for k, p in selected.items()},
        sources={k: sha(out / k) for k in sources}
        | {"price.hpp": sha(HERE / "price.hpp"), "build.py": sha(HERE / "build.py")},
    )
    with (out / "compiler.log").open("xb") as f:
        subprocess.run(cmd, check=True, stdout=f, stderr=subprocess.STDOUT, timeout=60)
    r.update(status="PASS_C110_PRICE_BUILD", binary_sha256=sha(out / "c110-price"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("parent", "source", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    r = dict(status="FAIL_PRESERVED", model_starts=0)
    try:
        build(a, r)
    except Exception as e:
        r["reason"] = f"{type(e).__name__}: {e}"
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
