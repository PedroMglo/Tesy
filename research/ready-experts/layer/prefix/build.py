"""Build the complete-consumer fixture with the sealed GGML loader and source closure."""

import argparse
import json
import os
import resource
import shutil
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
parent = run_path(HERE.parent / "build.py")["parent"]
STRONG = "59c0d7f98319a36c4ab00070a6739d18050a94fd1fd236c51f04dba91ae87c6d"
VARIANT = "c270-complete-prefix-consumer-v1"


def build(a):
    source = parent.sealed(HERE.parent / "native.cpp", STRONG).read_text()
    entry = "int main(int argc,char **argv)"
    parent.check(source.count(entry) == 1, "strong reference entry")
    generated = a.new_output_dir / "translation"
    generated.mkdir()
    (generated / "strong.inc").write_text(source.replace(entry, entry.replace("main", "full_cli")))
    for name in ("build.py", "protocol.md", "native.cpp"):
        shutil.copyfile(HERE / name, generated / name)
    parent.HERE = generated
    receipt = {}
    parent.build(a, receipt)
    receipt.update(
        status="PASS_READY_LAYER_BUILD",
        variant=VARIANT,
        tree=parent.git("rev-parse", "HEAD^{tree}"),
        strong_source_sha256=STRONG,
        strong_include_sha256=parent.sha(generated / "strong.inc"),
    )
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("old-build", "libs", "new-output-dir"):
        p.add_argument("--" + name, type=lambda s: Path(s).resolve(), required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        record = build(a)
    except Exception as exc:
        record = dict(status="FAIL_PRESERVED", reason=repr(exc))
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    print(record["status"], record.get("reason", ""))
    raise SystemExit(record["status"] == "FAIL_PRESERVED")
