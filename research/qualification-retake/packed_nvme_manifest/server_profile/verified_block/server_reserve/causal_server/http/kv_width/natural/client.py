"""Build a C291 client for the exact natural dispatch and bind both its target libraries."""

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
X = run_path(str(HERE.parent / "run.py"))
F, G, need, sha, save, Q = (X[k] for k in ("F", "G", "need", "sha", "save", "Q"))
METHOD = "66a4768178eeaa053cb9a31e0d70f68e8958864042efad0afc2ff8ee0deca645"
CUDA = "fedce434aa0098ff4b3701260bdb0b41586f6c642a863003e1ec339e81c74978"
BUILD = "2600bbaf6fc77dcf32731f25cd4a0e72425dc4187533085f31e5d5766716debf"
TEMPLATE = "8ded50541e00c395920eb5e690329ac5b923473b8e9b075dfb312af122aef2b7"


def fixture(a):
    gate = G["read"](a.failed / "receipt.json", TEMPLATE)
    log = next((a.failed / "ON/raw").glob("*.stderr"))
    need(sha(log) == gate["raw_sha256"][str(log.relative_to(a.failed))], "HTTP raw")
    cuts = [
        int(x)
        for x in re.findall(
            rb"task 0 \| cached n_tokens = ([0-9]+), memory_seq_rm", log.read_bytes()
        )
    ]
    need(cuts == [0, 61, 317, 573, 829, 1085, 1341, 1597, 1853], "external prompt geometry")
    d = F["F"]["inputs"](a)
    plan = G["read"](a.plan / "receipt.json", F["PLAN_PIN"])
    rows = G["read"](a.plan / "r0.stdout", plan["same_output_sha256"])
    row = next(v for v in rows["T1"] if v["proposal"])
    need(row["at"] == 20 and row["accepted"] == 2 and row["emitted"] == 3, "full first proposal")
    target = d["T1"]["target"]
    return dict(
        prompt=d["T1"]["prompt"],
        ends=cuts[1:] + [2043],
        prefix=target[:20],
        proposal=row["proposal"],
        expected=target[20:23],
    )


def build(a, out, r):
    prev = G["read"](a.previous / "receipt.json", F["S"]["CLIENT"])
    code = (a.previous / "reserve.cpp").read_text()
    need(
        sha(a.previous / "reserve.cpp") == prev["source_sha256"]
        and all(sha(Path(k)) == v for k, v in prev["headers"].items()),
        "C291 client and true headers",
    )
    gpu = G["read"](a.cuda / "receipt.json", CUDA)
    graph = G["read"](a.libraries / "receipt.json", BUILD)
    need(gpu["status"] == "GO_CUDA_WIDE_ATTENTION_OPERATOR" and len(gpu["rows"]) == 5, "GPU gate")
    static = G["read"](a.static / "receipt.json", G["STATIC"])["arms"]["C270_PACK"]
    original = Path(static["closure"]["libllama.so.0"]["file"])
    wide = a.libraries / "WIDE" / G["IMAGE"]
    data = fixture(a)
    save(out / "work.json", data)
    include = a.backend / "examples/gguf-hash/deps"
    sources = ("sha256/sha256.c", "sha256/sha256.h", "rotate-bits/rotate-bits.h")
    for key in sources:
        content = subprocess.check_output(
            [
                "git",
                "-C",
                a.backend,
                "show",
                F["F"]["OLD"]["C269"] + ":examples/gguf-hash/deps/" + key,
            ]
        )
        need((include / key).read_bytes() == content, "hash primitive")
    # Reuse the exercised snapshot, pool, row and mode helpers. Replace the narrow test workload.
    prefix = code[: code.index("void execute(")]
    begin = code.index("    const int reserve = product_reserve();", len(prefix))
    end = code.index("    std::cout<<", begin)
    body = (HERE / "natural.cpp.in").read_text().replace("@MODEL_AND_CONTEXT@", code[begin:end])
    native = out / "natural.cpp"
    native.write_text('#include "sha256/sha256.c"\n' + prefix + body)
    exe = out / "b3-numeric"
    argv = json.loads((a.previous / "compile.json").read_bytes())
    need(
        sha(Path(argv[0])) == "cef5002fbce633104c81b24e9fd935251ab653234c8dce8758d3c963d6123c8a"
        and argv.count(str(a.previous / "reserve.cpp")) == 1,
        "compiler",
    )
    argv[argv.index(str(a.previous / "reserve.cpp"))] = str(native)
    argv[argv.index("-MF") + 1] = str(out / "headers.d")
    argv[argv.index("-o") + 1] = str(exe)
    argv[1:1] = ["-I", str(include)]
    env = dict(PATH="/usr/bin:/bin", LANG="C", LC_ALL="C", CUDA_VISIBLE_DEVICES="", TMPDIR=str(out))
    G["command"](argv, out, out, "compile", env)
    dependencies = shlex.split(
        (out / "headers.d").read_text().replace(chr(92) + "\n", " ").split(":", 1)[1]
    )
    actual = {str(Path(v).resolve(strict=True)): sha(Path(v)) for v in dependencies}
    expected = dict(prev["headers"])
    del expected[str(a.previous / "reserve.cpp")]
    expected.update({str((include / k).resolve()): sha(include / k) for k in sources})
    expected[str(native)] = sha(native)
    need(actual == expected, "unchanged numerical headers and pinned SHA256")
    arms = {}
    for name, so, h in (
        ("HIST", original, G["PACK"]),
        ("WIDE", wide, graph["arms"]["WIDE"]["image_sha256"]),
    ):
        need(sha(so) == h, "native lib")
        env["LD_LIBRARY_PATH"] = os.pathsep.join([str(so.parent), *static["search"]])
        listing = subprocess.check_output(["/usr/bin/ldd", "-r", exe], text=True, env=env)
        need("not found" not in listing and "undefined symbol" not in listing, "native closure")
        (out / (name + ".ldd")).write_text(listing)
        selected = {
            k: str(v.resolve(strict=True)) for k, v in G["START"]["interpret"](listing).items()
        }
        need(
            selected
            == {k: v["file"] for k, v in static["closure"].items()} | {"libllama.so.0": str(so)},
            "providers",
        )
        need(
            subprocess.check_output([exe, "--self-test"], env=env) == b"PASS_NATURAL_HASH\n",
            "hash self-test",
        )
        arms[name] = dict(image=str(so), image_sha256=h, providers=len(selected))
    r.update(
        status="GO_NATURAL_CLIENT_ONLY",
        arms=arms,
        elf_sha256=sha(exe),
        headers=actual,
        work_sha256=sha(out / "work.json"),
        source_sha256=sha(native),
        cuda_gate_sha256=CUDA,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in (
        "previous",
        "cuda",
        "libraries",
        "failed",
        "backend",
        "static",
        "plan",
        "capture",
        "verified",
        "new-output-dir",
    ):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    t = time.monotonic()
    r = dict(status="FAIL_PRESERVED", model_starts=0, protocol_sha256=METHOD, commit=a.commit)
    try:
        h, r["tree"] = G["tree"](G["REPO"])
        cg = Path("/sys/fs/cgroup") / Path(
            Path("/proc/self/cgroup").read_text().strip()[3:]
        ).relative_to("/")
        need(
            h == a.commit
            and sha(HERE / "protocol.md") == METHOD
            and cg.name.startswith("tesy-natural-cut-")
            and (cg / "memory.max").read_text().strip() == str(3 << 30)
            and (cg / "memory.swap.max").read_text().strip() == "0",
            "source or scope",
        )
        build(a, out, r)
    except Exception as e:
        r.update(status="FAIL_PRESERVED", error=f"{type(e).__name__}: {e}")
    r["wall_s"] = time.monotonic() - t
    r["files"] = {f.name: sha(f) for f in out.iterdir() if f.is_file()}
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
