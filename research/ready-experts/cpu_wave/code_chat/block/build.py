"""Freeze actual server inputs and build a direct verifier from the pinned numerical client."""

import argparse
import os
import re
import struct
import subprocess
import time
from itertools import takewhile
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SRC = run_path(HERE.parent / "prefixes.py")
S, need, sha, read, save = (SRC[k] for k in ("S", "need", "sha", "read", "publish"))
OLD = "30fe606906a7b8862c7ba09d1832fdec0a04c50b3567a933abb38079176cc148"
CC = "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"


def work(prefix, family):
    public = read(HERE.parent / "prefixes.json")
    need(read(prefix / "receipt.json") == public, "sealed prefixes")

    def ids(desc):
        path = prefix / desc["file"]
        data = path.read_bytes()
        need(sha(path) == desc["sha256"] and len(data) == desc["ids"] * 4, "prefix IDs")
        return list(struct.unpack(f"<{desc['ids']}i", data))

    dataset = {k: ids(v) for k, v in public["files"].items()}
    root = read(family / "receipt.json")
    need(sha(family / "receipt.json") == public["family_sha256"], "historical family")
    trial = root["arms"][0]
    raw = family / "1R/raw"
    unit = trial["unit"]
    session = S["H"]["G"]["read"](raw.parent / "session.json", trial["session_sha256"])
    monitor = S["H"]["G"]["read"](raw / (unit + ".json"), session["monitor_sha256"])
    log = raw / (unit + ".stderr")
    need(sha(log) == monitor["output_sha256"][".stderr"], "natural journal")
    data = log.read_bytes()
    events = list(S["NATIVE"]["events"](data))
    tasks = [t for _, t, e in events if e == ("start",)]
    samples = [[e[3] for _, t, e in events if t == task and e[0] == "sample"] for task in tasks]
    starts = [
        [
            int(n)
            for t, n in re.findall(rb"task (\d+) \| cached n_tokens = (\d+), memory_seq_rm", data)
            if int(t) == task
        ]
        for task in tasks
    ]
    t1, t2, first = (dataset[k] for k in ("T1-prompt", "T2-prompt", "T1-output"))
    need(
        len(tasks) == 2 and samples[0] == first and len(first) == 78 and len(samples[1]) == 256,
        "native outputs",
    )
    need(
        all(
            S["NATIVE"]["digest"](S["NATIVE"]["ids_bytes"](s))
            == trial["target_ids"][str(i)]["sampled_sha256"]
            for i, s in enumerate(samples, 1)
        ),
        "sample seals",
    )
    need(
        starts == [[0, 61, 317, 573, 829, 1085, 1341, 1597, 1853], [2044, 2049]]
        and [len(t1), len(t2)] == [2043, 2105],
        "external boundaries",
    )
    common = sum(
        1
        for _ in takewhile(lambda pair: pair[0] == pair[1], zip(t1 + first[:-1], t2, strict=False))
    )
    need(common == public["t2_cached"] == starts[1][0], "true cache cut")
    cuts = []
    for c in public["cases"]:
        at, accepted = c["confirmed"], c["accepted"]
        inputs = ids(c["verifier_inputs"])
        need(
            ids(c["prefix"]) == samples[1][:at]
            and inputs[0] == samples[1][at - 1]
            and ids(c["serial_decisions"]) == samples[1][at : at + 1 + accepted]
            and inputs[1 : 1 + accepted] == samples[1][at : at + accepted]
            and (accepted == 2 or inputs[1 + accepted] != samples[1][at + accepted]),
            "causal cut",
        )
        cuts.append(
            dict(
                confirmed=at,
                accepted=accepted,
                inputs=inputs,
                position=c["first_model_input_position"],
            )
        )
    return dict(
        t1=t1,
        t2=t2,
        first=first,
        target=samples[1],
        cached=common,
        t1_ends=starts[0][1:] + [len(t1)],
        t2_ends=starts[1][1:] + [len(t2)],
        cases=cuts,
    )


def build(a, out):
    base = a.original
    receipt = read(base / "receipt.json")
    need(sha(base / "receipt.json") == OLD and sha(Path("/usr/bin/g++-15")) == CC, "build input")
    for name in ("compile-argv.json", "natural.cpp", "sha256.o"):
        need(sha(base / name) == receipt["files"][name], "original " + name)
    for path, digest in receipt["headers"].items():
        need(sha(Path(path)) == digest, "source or header " + Path(path).name)
    original = (base / "natural.cpp").read_text()
    prefix = original[: original.index("static void prefill(")]
    constructor = original[
        original.index("    const int reserve = product_reserve();") : original.index(
            "    prefill(ctx.get(),prompt,cuts);"
        )
    ]
    source = out / "code-cut.cpp"
    template = (HERE / "fixture.cpp.in").read_text()
    need(template.count("@MODEL_AND_CONTEXT@") == 1, "source anchor")
    source.write_text(prefix + template.replace("@MODEL_AND_CONTEXT@", constructor))
    save(out / "work.json", work(a.prefix, a.family))
    exe = out / "code-cut"
    replace = {
        str(base / "natural.cpp"): str(source),
        str(base / "headers.d"): str(out / "headers.d"),
        str(base / "b3-numeric"): str(exe),
    }
    argv = [replace.get(w, w) for w in read(base / "compile-argv.json")]
    save(out / "argv.json", argv)
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=160)
    headers = {
        Path(k).resolve(strict=True)
        for k in (out / "headers.d").read_text().replace("\\\n", " ").split(":", 1)[1].split()
    }
    expected = {
        Path(k).resolve(strict=True)
        for k in receipt["headers"]
        if not k.endswith(("sha256.c", "rotate-bits.h", "natural.cpp"))
    }
    need(headers == expected | {source}, "generated include closure")
    test = subprocess.run(
        [exe, "--self-test"], capture_output=True, text=True, check=True, timeout=20
    )
    need(test.stdout.strip() == "PASS_CODE_CUT_HASH", "model-free binary")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    return dict(
        status="BUILT_CODE_CUT",
        commit=commit,
        original_sha256=OLD,
        compiler_sha256=CC,
        model_launches=0,
        protocol_sha256=sha(HERE / "protocol.md"),
        files={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("original", "prefix", "family", "new-output-dir"):
        parser.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    start = time.monotonic()
    try:
        result = build(a, a.new_output_dir)
    except Exception as exc:
        save(
            a.new_output_dir / "failure.json",
            dict(status="FAIL_PRESERVED", reason=str(exc), elapsed_s=time.monotonic() - start),
        )
        raise
    save(a.new_output_dir / "receipt.json", result | dict(elapsed_s=time.monotonic() - start))
    print(result["status"])
