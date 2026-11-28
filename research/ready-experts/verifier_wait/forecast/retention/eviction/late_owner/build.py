"""Build a private retained-read numerical client against the sealed C291 ABI."""

import argparse
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
U = run_path(HERE.parent / "consumer_build.py")
need, sha, save, verified = (U[k] for k in ("need", "sha", "save", "verified"))
SYMBOLS = (
    "pread",
    "ggml_backend_tensor_set",
    "_ZNSt18condition_variable10notify_allEv",
    "_Z25llama_moe_stream_wave_idsP11ggml_tensoriiPv",
    "_ZN16llama_moe_stream19reserve_slot_lockedER22llama_moe_stream_layerii",
)
BASE = "dd2067917d32c970d645fee0f622f194e2a0fce422032d0b6de541fca62ff1b1"


def render(source):
    parent = (HERE.parent / "consumer.cpp.in").read_text()
    helpers = (
        parent[: parent.index("static void entry_start")]
        + parent[parent.index("static std::string entry_pool") :]
    )
    prompt = (
        "        auto v = measured(model.get(), observe, false, "
        "[&]{prompt_return(ctx.get(),t2,pos,end);});"
    )
    step = '        v["at"] = confirmed;'
    for old, new in (
        (
            "namespace {\nnamespace fs",
            (HERE / "delivery.cpp.in").read_text() + "\nnamespace {\nnamespace fs",
        ),
        (
            "static void run_wait(",
            helpers + "\n" + (HERE / "client.cpp.in").read_text() + "\nstatic void run_wait(",
        ),
        (
            "    llama_memory_clear(mem,true);\n    std::array",
            '    owner_start(model.get(),w.at("owner_plan"),w.at("owner_mode"));\n'
            "    llama_memory_clear(mem,true);\n    std::array",
        ),
        (
            prompt,
            """        const bool active=end-pos==148;
        auto start=owner_probe::stamp();
        if (active) owner_arm(w.at("owner_plan"));
        auto armed=owner_probe::stamp();
"""
            + prompt
            + """
        auto returned=owner_probe::stamp();
        if (active) {
            owner_close(w.at("owner_plan"));
            auto closed=owner_probe::stamp();
            auto report=owner_report(w.at("owner_plan"));
            report["arm_ns"]=armed-start;
            report["forward_ns"]=returned-armed;
            report["cleanup_ns"]=closed-returned;
            report["all_ns"]=closed-start;
            report["whole_ns"]=closed-owner_probe::table.train_start;
            report["pool148"]=entry_pool(model.get(),out,"owner148");
            data["entry_delivery"]=std::move(report);
        }""",
        ),
        (
            step,
            '        if (confirmed==1) data["entry_delivery"]["pool_first_decode"]='
            'entry_pool(model.get(),out,"first-decode");\n'
            + step,
        ),
    ):
        need(source.count(old) == 1, "sealed client anchor")
        source = source.replace(old, new)
    return source


def build(a, out):
    commit, tree = U["M"]["B"]["version"]()
    need(commit == a.commit, "clean pinned checkout")
    base = verified(a.parent / "receipt.json", U["PARENT"])
    need(
        all(sha(a.parent / k) == v for k, v in base["files"].items())
        and sha(Path(base["argv"][0])) == base["compiler_sha256"],
        "original binary, inputs and compiler",
    )
    prior = verified(a.entry / "receipt.json", BASE)
    plan = dict(prior["plan"])
    plan["records"] = [r for r in plan["records"] if r["layer"] != 14 or r["expert"] == 54]
    need(
        (len(plan["records"]), sum(r["uses"] for r in plan["records"])) == (69, 70), "frozen cohort"
    )
    source = out / "code-cut.cpp"
    source.write_text(render((a.parent / source.name).read_text()))
    argv = [str(out / Path(v).name) if Path(v).parent == a.parent else v for v in base["argv"]]
    idx = argv.index("-o")
    argv[idx:idx] = ["-Wl,--export-dynamic-symbol=" + sym for sym in SYMBOLS]
    with (out / "compiler.log").open("x") as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=150)
    expected = U["headers"](a.parent / "headers.d") - {a.parent / source.name}
    need(U["headers"](out / "headers.d") - {source} == expected, "project header closure")
    exe = out / "code-cut"
    need(
        subprocess.check_output([exe, "--self-test"], text=True).strip() == "PASS_CODE_CUT_HASH",
        "numerical self-test",
    )
    symbols = subprocess.check_output(["readelf", "--dyn-syms", "--wide", exe], text=True)
    exported = {s.split()[-1] for s in symbols.splitlines() if " GLOBAL " in s and " UND " not in s}
    need(set(SYMBOLS) <= exported, "provider, wave and publication hooks")
    work = verified(a.parent / "work.json", U["F"]["WORK"])
    modes = {}
    for mode in "RVOH":
        dest = out / mode
        dest.mkdir()
        os.link(exe, dest / "code-cut")
        save(dest / "work.json", work | dict(owner_plan=plan, owner_mode=mode))
        modes[mode] = {k: sha(dest / k) for k in ("code-cut", "work.json")}
    return dict(
        status="BUILT",
        commit=commit,
        tree=tree,
        source=sha(source),
        compiler=base["compiler_sha256"],
        argv=argv,
        baseline=U["PARENT"],
        entry=BASE,
        protocol=sha(HERE / "provider.md"),
        inputs={k: sha(HERE / k) for k in ("delivery.cpp.in", "client.cpp.in", "build.py")},
        plan=plan,
        modes=modes,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "entry", "new-output-dir"):
        p.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        result = build(args, args.new_output_dir)
        save(args.new_output_dir / "receipt.json", result)
        print(result["status"], result["modes"]["H"]["code-cut"])
    except Exception as exc:
        save(args.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
