"""Add live, zero-load shadow forwards to the sealed numerical probe."""

import argparse
import os
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(HERE / "build.py")
need, sha, read, save = (BASE[k] for k in ("need", "sha", "read", "save"))
PARENT = "ef82a43dfb9b72d48a5693991d63c4fa19c0fc9a9d52c7da5d0a9fe7c05e0764"


def build(a, out):
    old = read(a.parent / "receipt.json")
    need(
        sha(a.parent / "receipt.json") == PARENT
        and all(sha(a.parent / k) == h for k, h in old["files"].items()),
        "sealed barrier probe",
    )
    for path, h in read(a.original / "receipt.json")["headers"].items():
        need(sha(Path(path)) == h, "header " + path)
    need(
        sha(a.original / "receipt.json") == BASE["B"]["OLD"]
        and sha(Path(old["argv"][0])) == old["compiler_sha256"],
        "pinned compiler and header list",
    )
    source = (a.parent / "code-cut.cpp").read_text()
    hot = (HERE / "hot.cpp.in").read_text()
    start = "static void run_wait("
    forward = (
        "        auto v = measured(model.get(),observe,true,[&]{supplied(ctx.get(),pos,tokens);});"
    )
    decision = "        int keep = 0, accepted = 0;"
    for marker, replacement in (
        (start, hot + "\n" + start),
        (forward, "        const auto entry = sequence_view(ctx.get());\n" + forward),
        (
            decision,
            '        v["hot"] = hot_replays(ctx.get(),model.get(),entry,tokens,pos,v);\n'
            + decision,
        ),
    ):
        need(source.count(marker) == 1, "source anchor")
        source = source.replace(marker, replacement)
    (out / "code-cut.cpp").write_text(source)
    save(
        out / "work.json",
        read(a.parent / "work.json") | dict(hot_protocol_sha256=sha(HERE / "hot-protocol.md")),
    )
    cmd = [str(out / Path(s).name) if Path(s).parent == a.parent else s for s in old["argv"]]
    save(out / "argv.json", cmd)
    with (out / "compiler.log").open("xb") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=150)

    def headers(root):
        return {
            Path(k).resolve()
            for k in (root / "headers.d").read_text().replace("\\\n", " ").split(":", 1)[1].split()
        } - {root / "code-cut.cpp"}

    need(headers(a.parent) == headers(out), "identical compiled include set")
    need(
        subprocess.check_output([out / "code-cut", "--self-test"], text=True).strip()
        == "PASS_CODE_CUT_HASH",
        "native self-test",
    )
    return dict(
        protocol_sha256=sha(HERE / "hot-protocol.md"),
        native_source_sha256=sha(HERE / "hot.cpp.in"),
        parent_sha256=PARENT,
        compiler_sha256=old["compiler_sha256"],
        argv=cmd,
        model_starts=0,
        files={p.name: sha(p) for p in out.iterdir() if p.is_file()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("parent", "original", "new-output-dir"):
        p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    out.mkdir()
    try:
        save(out / "receipt.json", build(a, out))
    except Exception as exc:
        save(out / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    print("BUILT_HOT_VERIFIER")
