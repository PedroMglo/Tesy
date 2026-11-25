"""Build one additive observation on the pinned C291 decode fixture via its qualified recipe."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "cpu/build.py"
BASE_HASH = "f0fa790f6532de9a3464624db28da35091c9d130df9ea4276ce31116183fa58b"
if hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_HASH:
    raise ValueError("historical build source")
spec = importlib.util.spec_from_file_location("split_cpu_build", BASE)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
FILES = ("engine.inc", "split_graph.inc", "build.py", "protocol.md", "repair.md")


def materialize(source):
    context = "json run(const fs::path &prefill,"
    returned = '    return {{"mode",state.mode},{"before",before}'
    if source.count(context) != 1 or source.count(returned) != 1:
        raise ValueError("historical cut ambiguous")
    return source.replace(context, '#include "engine.inc"\n' + context).replace(
        returned, "    run_split(cpu.get(),in,w.physical,ref,out);\n" + returned
    )


def build(a, r):
    old = json.loads(parent.sealed(a.old_build / "receipt.json", parent.OLD).read_bytes())
    original = parent.sealed(parent.DECODE / "decode.cpp", old["source_sha256"]["decode.cpp"])
    generated = a.new_output_dir / "source"
    generated.mkdir()
    (generated / "native.cpp").write_text(materialize(original.read_text()))
    for name in FILES:
        (generated / name).write_bytes((HERE / name).read_bytes())
    parent.HERE = generated
    parent.build(a, r)
    r.update(
        status="PASS_RANK_SPLIT_CPU_BUILD",
        recipe_sha256=BASE_HASH,
        generated_sha256=parent.sha(generated / "native.cpp"),
        parent_decode_sha256=parent.sha(original),
        source_sha256={n: parent.sha(HERE / n) for n in FILES},
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("old-build", "libs", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    r = {"status": "FAIL_PRESERVED"}
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        build(a, r)
    except Exception as exc:
        r.update(status="FAIL_PRESERVED", reason=repr(exc))
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
