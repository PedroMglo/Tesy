"""Build a private numerical probe against the qualified client and the two nominal turns."""

import argparse
import hashlib
import json
import os
import struct
import subprocess
from itertools import takewhile
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BLOCK = HERE.parent / "cpu_wave/code_chat/block"
B = run_path(BLOCK / "build.py")
need, sha, read, save = (B[k] for k in ("need", "sha", "read", "save"))
CLIENT = "d8c39a975aea3fe9022c371f4bf13ad9b908d94f9647838d81babc7b99845745"
INPUT = "17285d7438cedc23a0db6c119ee8a315eb06b4a45ab97aeaef623bb25c20c356"
CAUSAL = run_path(HERE.parent / "draft20/joint/suffix.py")


def prepare(a, out):
    old, src = read(a.client / "receipt.json"), a.client / "code-cut.cpp"
    need(
        sha(a.client / "receipt.json") == CLIENT and sha(a.original / "receipt.json") == B["OLD"],
        "numerical client identity",
    )
    for name, digest in old["files"].items():
        need(sha(a.client / name) == digest, "input " + name)
    source_headers = read(a.original / "receipt.json")["headers"]
    for name, digest in source_headers.items():
        need(sha(Path(name)) == digest, "pinned numerical header")
    args = read(a.client / "argv.json")
    need(
        sha(Path(args[0])) == B["CC"] and sha(a.inputs / "receipt.json") == INPUT,
        "compiler or nominal inputs",
    )
    reference = read(a.inputs / "receipt.json")
    w = read(a.client / "work.json")
    family = read(a.family / "receipt.json")
    need(
        sha(a.family / "receipt.json") == reference["cases"]["nominal"][0]["family_sha256"],
        "nominal conversation",
    )
    r = family["arms"][2]
    for field, seal in (
        ("t1", r["turns"][0]["official_ids_sha256"]),
        ("first", r["target_ids"]["1"]["sampled_sha256"]),
    ):
        need(
            hashlib.sha256(struct.pack(f"<{len(w[field])}i", *w[field])).hexdigest() == seal,
            "common first turn",
        )
    for field, suffix in (("t2", "prompt"), ("target", "target")):
        p = a.inputs / ("nominal-" + suffix + ".i32")
        need(sha(p) == reference["files"][p.name], p.name)
        w[field] = [v for (v,) in struct.iter_unpack("<i", p.read_bytes())]
    common = sum(
        1
        for _ in takewhile(
            lambda q: q[0] == q[1], zip(w["t1"] + w["first"][:-1], w["t2"], strict=False)
        )
    )
    need(common == w["cached"] == 2044 and len(w["t2"]) == 2197, "prompt cache prefix")
    w["t2_ends"] = [2049, 2197]
    del w["cases"]
    old_n2 = CAUSAL["N2"]
    need(
        sha(old_n2) == "797746256c463790abc44463e56948636fa63b03f9d0e710daa29203f8a9846e",
        "N2 source",
    )
    seq, _, _ = CAUSAL["replay"](
        CAUSAL["Scan"](run_path(old_n2)["draft"]), w["t2"], w["target"], 256, 200002
    )
    published = read(HERE.parent / "draft20/joint/evidence-20261128-r01/combined.json")
    need(
        [[at, len(q), depth, n] for at, q, depth, n in seq]
        == published["receipts"][0]["cases"]["nominal"]["N2"]["rows"],
        "historical schedule",
    )
    w["schedule"] = seq
    w["keep_counts"] = [
        next(at + n for at, q, d, n in seq if q and d == depth) for depth in (0, 2)
    ] + [len(w["target"])]
    save(out / "work.json", w)
    original = src.read_text()
    setup = original.split("    const auto first = w.at(", 1)[1]
    setup = setup[
        setup.index("    const int reserve =") : setup.index("    prompt_span(ctx.get(), t2")
    ]
    need(setup.count('role == "ON" ? 3 : 1') == 1, "reserve source")
    setup = setup.replace('role == "ON" ? 3 : 1', "serial ? 1 : 3")
    cpp = out / "code-cut.cpp"
    template = (HERE / "probe.cpp.in").read_text()
    need(template.count("@SETUP_AND_T1@") == 1, "context placeholder")
    cpp.write_text(
        original[: original.index("static void run_cut(")]
        + template.replace("@SETUP_AND_T1@", setup)
    )
    cmd = [str(out / Path(arg).name) if Path(arg).parent == a.client else arg for arg in args]
    save(out / "argv.json", cmd)
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=150, check=True)

    def headers(p):
        return {
            Path(k).resolve() for k in p.read_text().replace("\\\n", " ").split(":", 1)[1].split()
        }

    need(
        headers(out / "headers.d") == (headers(a.client / "headers.d") - {src}) | {cpp},
        "actual header closure",
    )
    need(
        subprocess.check_output([out / "code-cut", "--self-test"], text=True).strip()
        == "PASS_CODE_CUT_HASH",
        "probe self-test",
    )
    return dict(
        protocol_sha256=sha(HERE / "protocol.md"),
        native_source_sha256=sha(HERE / "probe.cpp.in"),
        inputs_sha256=INPUT,
        client_sha256=CLIENT,
        original_sha256=B["OLD"],
        compiler_sha256=B["CC"],
        family_sha256=sha(a.family / "receipt.json"),
        argv=cmd,
        model_starts=0,
        files={p.name: sha(p) for p in out.iterdir() if p.is_file()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("client", "original", "inputs", "family", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        save(a.new_output_dir / "receipt.json", prepare(a, a.new_output_dir))
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_text(
            json.dumps(dict(status="FAIL_PRESERVED", error=str(exc)))
        )
        raise
    print("BUILT_VERIFIER_WAIT")
