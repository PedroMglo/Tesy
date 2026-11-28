"""Build the bounded reader or bind both forecast policies to authenticated target pack offsets."""

import argparse
import os
import re
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
J = run_path(HERE.parent / "joint.py")
P, F, S = (J[k] for k in ("P", "F", "S"))
need, sha, verified, load, save = (F[k] for k in ("need", "sha", "verified", "load", "save"))
R = HERE.parents[2] / "renewal/reader"
B = run_path(R / "build.py")
sha = B["sha"]
PREP = run_path(R / "prepare.py")
PROTOCOL = "951b13446a01651c2b08ee4781ee46e3ec64860e91298c65e44d10a2ed7d3b15"
CERT = "f0a77937a5516eb4874a8aa03fdac6c204042a2d31fc2e7fe659604357a9d680"
HISTORIC_BUILD = "8f16976da52f529c3ac8dd72641acf8a2da73906b0ec2748e10fbc78f808a464"
CUT = 383144
STAT = ("dev", "inode", "size_bytes", "mtime_ns", "ctime_ns")


def build(a):
    old = verified(a.previous / "receipt.json", HISTORIC_BUILD)
    need(
        sha(R / "native.cpp") == old["native_sha256"]
        and sha(a.rpm) == B["PACKAGE"]
        and sha("/usr/bin/g++") == old["compiler_sha256"],
        "compiler, ring source or RPM",
    )
    subprocess.run(["rpmkeys", "--checksig", a.rpm], check=True)
    content = subprocess.check_output(["rpm2cpio", a.rpm], timeout=10)
    dest = a.new_output_dir
    subprocess.run(
        ["cpio", "-idm", "--quiet", "./usr/include/*"], input=content, cwd=dest, check=True
    )
    original = (R / "native.cpp").read_text()
    need(original.count("int main(int argc") == 1, "reader source boundary")
    src = dest / "reader.cpp"
    src.write_text(original.split("int main(int argc")[0] + (HERE / "reader.cpp.in").read_text())
    exe = dest / "reader"
    cmd = [
        "/usr/bin/g++",
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pthread",
        "-I",
        str(dest / "usr/include"),
        str(src),
        "-l:liburing.so.2",
        "-lcrypto",
        "-o",
        str(exe),
    ]
    with (dest / "compiler.log").open("x") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45)
    ldd = subprocess.check_output(["ldd", exe], text=True, timeout=5)
    (dest / "ldd.txt").write_text(ldd)
    libs = {p: sha(p) for p in re.findall(r"(/\S+) \(0x", ldd)}
    need("not found" not in ldd and libs == old["libraries"], "reader libraries changed")
    return dict(
        command=cmd,
        compiler=old["compiler_sha256"],
        rpm=B["PACKAGE"],
        libraries=libs,
        binary=sha(exe),
        source=sha(src),
        parent=HISTORIC_BUILD,
    )


def enumerate_step(model, token, layers, memory, at, joint):
    predicted = [
        F["choices"](
            *model.token_scores(token, layer), memory.resident(layer), model.marginal[layer]
        )[0]
        for layer in range(36)
    ]
    cold_keys, all_keys = set(), set()
    for layer in range(36):
        dest = layer + 2
        if dest < 36:
            score, _ = model.upstream_scores(layers[layer], dest)
            held = memory.resident(dest)
            offered = sorted(
                (e for e in score if score[e] > 0 and e not in held), key=lambda e: (-score[e], e)
            )[:4]
            predicted[dest].update(e for e in offered if score[e] >= CUT)
        tx = memory.by_site[at, layer]
        cold = sorted(row[5] for row, effect in tx if effect[1] is None)
        mask = sum(1 << i for i, e in enumerate(cold) if e in predicted[layer])
        need(
            joint[layer] == [len(predicted[layer]), mask],
            "forecast count, deduplication or identity",
        )
        cold_keys.update((layer, e) for e in cold)
        all_keys.update((layer, e) for e in predicted[layer])
        for row, effect in tx:
            memory.apply(row, effect)
    return cold_keys, all_keys | cold_keys


def plan(a):
    out = a.new_output_dir
    base = verified(F["CONTROL"], F["CONTROL_SHA"])
    joint_path = HERE.parent / "evidence-joint-20261128-r01"
    certificate = verified(joint_path / "receipt.json", CERT)
    options = verified(joint_path / "scores.json.gz", certificate["scores"])
    ref = verified(J["BASE"] / "witness.json.gz", J["WITNESS_SHA"])
    frozen = J["materialize"](ref["calls"], J["events"](options["calls"]), True, CUT)
    need(
        certificate["result"]["8000000000"]["joint"]["best"]["all"]["threshold"] == CUT,
        "diagnostic policy",
    )
    train = load(J["BASE"] / "train.json")
    model = F["Frequencies"].unpack(verified(a.trained / "model.json.gz", train["table"]))
    w = verified(a.work, F["WORK"])
    physical = verified(a.serial, F["SERIAL"])
    journal = a.arm / "observer/events.pfj"
    need(sha(journal) == F["JOURNAL"], "journal identity")
    profile = F["PROFILE"]
    cut, end = profile["metadata"](journal, True)
    need(cut == train["records"], "T1 cut")
    memory = F["Inventory"](verified(S["PATHS"]["transactions"], base["inputs"]["transactions"]))
    manifest = verified(a.manifest / "receipt.json", PREP["MANIFEST"])
    index = verified(a.manifest / "integral-index.json", manifest["index_sha256"])
    experts = {(e["layer"], e["expert"]): e for e in index["experts"]}
    need(len(experts) == 4608 and index["weight_window"] == P["SIZE"], "pack layout")
    sources = [[], []]
    token = w["target"][0]
    calls = 0
    for i, (pos, layers) in enumerate(
        F["positions"](profile["iter_rows"](journal, cut, end - cut))
    ):
        need(pos == 2044 + i, "input order")
        if pos < len(w["t2"]):
            model.observe(w["t2"][pos], layers)
            continue
        r = physical["decode"][calls]
        need(
            token == w["target"][calls]
            and r["at"] == calls + 1
            and all(set(r["routes"][layer]) == set(ids) for layer, ids in layers.items()),
            "physical target",
        )
        pair = enumerate_step(model, token, layers, memory, calls + 1, frozen[calls])
        for keys, seq in zip(pair, sources, strict=True):
            seq.append(sorted((experts[k] for k in keys), key=lambda e: e["pack_offset"]))
        model.observe(token, layers)
        (token,) = r["ids"]
        calls += 1
    need(calls == 46 and token == w["target"][-1], "terminal target")
    counts = [[len(row) for row in mode] for mode in sources]
    need(
        [sum(n) for n in counts] == [788, 2662] and [sum(n[:44]) for n in counts] == [768, 2514],
        "read census",
    )
    records = set()
    windows = out / "windows.tsv"
    with windows.open("x") as f:
        for idx, mode in enumerate(sources):
            for at, step in enumerate(mode, 1):
                for e in step:
                    off = e["pack_offset"]
                    components = e["components"][:3]
                    need(
                        off % 4096 == 0
                        and [v["packed_relative_offset"] for v in components]
                        == [0, 4406400, 8812800]
                        and all(
                            v["type"] == "mxfp4" and v["size_bytes"] == 4406400 for v in components
                        ),
                        "target component geometry",
                    )
                    records.add(off)
                    print(idx, at, off, *(m["sha256"] for m in components), sep="\t", file=f)
    return dict(
        counts=counts,
        unique=len(records),
        windows=sha(windows),
        joint=CERT,
        manifest=PREP["MANIFEST"],
        index=manifest["index_sha256"],
        pack_path=manifest["pack_path"],
        pack_stat=[manifest["pack_stat"][k] for k in STAT],
        pack=manifest["pack_sha256"],
        model_path=manifest["model_path"],
        model_stat=[manifest["model_stat"][k] for k in STAT],
        model=manifest["model_sha256"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="action", required=True)
    for name, keys in (
        ("build", ("previous", "rpm")),
        ("plan", ("work", "trained", "serial", "arm", "manifest")),
    ):
        q = subs.add_parser(name)
        for k in (*keys, "new-output-dir"):
            q.add_argument("--" + k, required=True, type=lambda s: Path(s).resolve())
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        commit, tree = B["version"]()
        need(sha(HERE / "protocol.md") == PROTOCOL, "physical protocol")
        data = (build if a.action == "build" else plan)(a)
        save(
            a.new_output_dir / "receipt.json",
            data
            | dict(
                status="PASS",
                commit=commit,
                tree=tree,
                protocol=PROTOCOL,
                program=sha(Path(__file__)),
            ),
        )
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
