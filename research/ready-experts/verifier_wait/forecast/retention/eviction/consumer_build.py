"""Build a private numerical client that delivers 74 authenticated live primary records."""

import argparse
import os
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "release.py")
F, S, E, M, need, sha, verified, save = (
    P[k] for k in ("F", "S", "E", "M", "need", "sha", "verified", "save")
)
PROTO = "61e7c965e104a6ed974c3a1e91c201435c42df62f4f51c901ebba38c23842228"
PARENT = "ef82a43dfb9b72d48a5693991d63c4fa19c0fc9a9d52c7da5d0a9fe7c05e0764"
ORDER = ("ref", "parity", "r1", "o1", "h1", "h2", "o2", "r2")


def records(manifest):
    parent = verified(F["CONTROL"], F["CONTROL_SHA"])
    tx = verified(S["PATHS"]["transactions"], parent["inputs"]["transactions"])
    _, early, whole, _ = E["inventory"](tx)
    primary = {(layer, s): (expert, g) for layer, s, expert, g in tx["initial"]}
    for c, _, layer, s, g, expert, old in tx["reservations"]:
        if c != 1:
            break
        need(primary[layer, s] == (old, g - 1), "first call generation")
        primary[layer, s] = expert, g
    where = {(layer, expert): (s, g) for (layer, s), (expert, g) in primary.items()}
    keys = {
        (layer, e)
        for site, exp in whole.items()
        for c, _, layer in (site,)
        if c == 2
        for e in exp - early.get(site, set())
        if (layer, e) in where
    }
    uses = Counter((layer, e) for c, _, layer, _, _, e, _ in tx["reservations"] if c == 2)
    need(
        len(keys) == 74
        and sum(layer < 25 for layer, e in keys) == 49
        and sum(uses.values()) == 1212,
        "population or return",
    )
    ref = verified(manifest / "receipt.json", M["PREP"]["MANIFEST"])
    idx = verified(manifest / "integral-index.json", ref["index_sha256"])
    result = []
    for layer, e in sorted(keys):
        r = idx["experts"][128 * layer + e]
        parts = r["components"][:3]
        need(
            (r["layer"], r["expert"], r["pack_offset"])
            == (layer, e, (128 * layer + e) * idx["stride"])
            and [p["packed_relative_offset"] for p in parts] == [0, 4406400, 8812800]
            and all(p["size_bytes"] == 4406400 and p["type"] == "mxfp4" for p in parts),
            "slot and direct window",
        )
        s, g = where[layer, e]
        result.append(
            dict(
                layer=layer,
                expert=e,
                slot=s,
                generation=g,
                uses=uses[layer, e],
                matrices=[p["sha256"] for p in parts],
            )
        )
    return dict(
        stride=idx["stride"],
        pack_stat=[ref["pack_stat"][k] for k in M["STAT"]],
        records=result,
        pack=ref["pack_sha256"],
        model=ref["model_sha256"],
        index=ref["index_sha256"],
    )


def render(source):
    seq = (
        "        auto v = measured(model.get(), observe, false, "
        "[&]{prompt_return(ctx.get(),t2,pos,end);});"
    )
    insert = (
        """        const bool active = end-pos==148;
        const auto start=now_ns();
        if (active) entry_start(model.get(),w.at("entry_plan"),w.at("entry_mode"));
        const auto captured=now_ns();
"""
        + seq
        + """
        const auto before_cleanup=now_ns();
        if (active) {
            auto result=entry_stop(model.get(),w.at("entry_plan"),w.at("entry_mode"));
            const auto done=now_ns();
            result["capture_ns"]=captured-start;
            result["forward_ns"]=before_cleanup-captured;
            result["cleanup_ns"]=done-before_cleanup;
            result["all_ns"]=done-start;
            result["pool148"]=entry_pool(model.get(),out,"entry148");
            data["entry_delivery"]=std::move(result);
        }"""
    )
    step = '        v["at"] = confirmed;'
    for anchor, replacement in (
        (
            "namespace {\nnamespace fs",
            (HERE / "dispatch.cpp.in").read_text() + "\nnamespace {\nnamespace fs",
        ),
        (
            "static void run_wait(",
            (HERE / "consumer.cpp.in").read_text() + "\nstatic void run_wait(",
        ),
        (seq, insert),
        (
            step,
            '        if (confirmed==1) data["entry_delivery"]["pool_first_decode"]='
            'entry_pool(model.get(),out,"first-decode");\n'
            + step,
        ),
    ):
        need(source.count(anchor) == 1, "numerical source anchor")
        source = source.replace(anchor, replacement)
    return source


def headers(file):
    return {
        Path(s).resolve() for s in file.read_text().replace("\\\n", " ").split(":", 1)[1].split()
    }


def build(a, out):
    need(sha(HERE / "consumer.md") == PROTO, "physical protocol")
    commit, tree = M["B"]["version"]()
    old = verified(a.parent / "receipt.json", PARENT)
    need(
        all(sha(a.parent / k) == v for k, v in old["files"].items())
        and sha(Path(old["argv"][0])) == old["compiler_sha256"],
        "original client and compiler",
    )
    src = out / "code-cut.cpp"
    src.write_text(render((a.parent / src.name).read_text()))
    cmd = [str(out / Path(v).name) if Path(v).parent == a.parent else v for v in old["argv"]]
    cmd.insert(cmd.index("-o"), "-Wl,--export-dynamic-symbol=pread")
    save(out / "argv.json", cmd)
    with (out / "compiler.log").open("x") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=150, check=True)
    base = headers(a.parent / "headers.d") - {a.parent / src.name}
    need(headers(out / "headers.d") - {src} == base, "same project and target headers")
    exe = out / "code-cut"
    need(
        subprocess.check_output([exe, "--self-test"], text=True).strip() == "PASS_CODE_CUT_HASH",
        "client self-test",
    )
    symbols = subprocess.check_output(["readelf", "--dyn-syms", "--wide", exe], text=True)
    need(
        any(
            " GLOBAL " in line and " UND " not in line and line.split()[-1] == "pread"
            for line in symbols.splitlines()
            if line.strip()
        ),
        "public read adapter",
    )
    plan = records(a.manifest)
    work = verified(a.parent / "work.json", F["WORK"])
    modes = {}
    for mode in "RVHO":
        dest = out / mode
        dest.mkdir()
        os.link(exe, dest / "code-cut")
        save(dest / "work.json", work | dict(entry_plan=plan, entry_mode=mode))
        modes[mode] = {k: sha(dest / k) for k in ("code-cut", "work.json")}
    return dict(
        commit=commit,
        tree=tree,
        protocol=PROTO,
        parent=PARENT,
        argv=cmd,
        compiler=old["compiler_sha256"],
        source=sha(src),
        modes=modes,
        plan=plan,
        programs={
            k: sha(HERE / k) for k in ("dispatch.cpp.in", "consumer.cpp.in", "consumer_build.py")
        },
        expected_hits=sum(r["uses"] for r in plan["records"]),
        status="BUILT",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("parent", "manifest", "new-output-dir"):
        p.add_argument("--" + n, type=lambda x: Path(x).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    dest = a.new_output_dir
    dest.mkdir()
    try:
        result = build(a, dest)
        save(dest / "receipt.json", result)
        print(result["status"], sha(dest / "receipt.json"), result["expected_hits"])
    except Exception as exc:
        save(dest / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
