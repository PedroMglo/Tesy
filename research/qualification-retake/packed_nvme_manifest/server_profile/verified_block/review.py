"""Reopen both scientific attempts, including archived SONAME aliases, without a model."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "build.py"))
need, read, sha = (B[k] for k in ("need", "read", "sha"))
CURRENT = "55a0322b12a108fa1b15ab01ac8a7f4194934d32b659f2cd97f0c17ae20ed59b"


def reopen(root, authority):
    r = read(root / "receipt.json", authority)
    checked = {"receipt.json"}
    for key, value in r["files"].items():
        file = root / key
        need(not file.is_symlink() and sha(file) == value, key)
        checked.add(key)
    for name, arm in r["arms"].items():
        alias = root / name / "libllama.so.0"
        file = alias.parent / B["IMAGE"]
        need(sha(file) == arm["image_sha256"] and B["ABI"](file) == arm["abi"], name)
        if alias.is_symlink():
            need(os.readlink(alias) == file.name, "alias target")
        else:
            alias = alias.with_name("alias.json")
            record = json.loads(alias.read_bytes())
            need(record == dict(alias="libllama.so.0", target=file.name, sha256=sha(file)), "alias")
        checked.add(str(alias.relative_to(root)))
    need(checked == {str(f.relative_to(root)) for f in root.rglob("*") if f.is_file()}, "coverage")
    return r


def review(first, second):
    a = reopen(first, B["FIRST_LINK"])
    b = reopen(second, CURRENT)
    img = B["IMAGE"]
    need(
        a["status"] == "FAIL_PRESERVED"
        and a["stage"] == "RELINK"
        and b["status"] == "GO_STATIC_COMBINED_PACK_BLOCK"
        and b["first_link_sha256"] == B["FIRST_LINK"]
        and a["model_starts"] == b["model_starts"] == a["server_starts"] == b["server_starts"] == 0
        and (first / "RELINK" / img).read_bytes() == (second / "RELINK" / img).read_bytes(),
        "terminal controls",
    )
    inputs = [
        json.loads((second / n / "headers.json").read_bytes()) for n in ("RECOMPILE", "BLOCK")
    ]
    common = inputs[0].keys() & inputs[1].keys()
    need(
        len(common) == len(inputs[0]) - 1 == len(inputs[1]) - 1 == 342
        and all(inputs[0][h] == inputs[1][h] for h in common),
        "common headers",
    )
    arms = {}
    for name, record in sorted(b["arms"].items()):
        rows = {}
        for key, count in (("C270_PACK", 18), ("C281_PACK", 24)):
            log = (second / name / (key + ".log")).read_text()
            providers = B["START"]["interpret"](log)
            proof = record["relocation"][key]
            need(
                len(providers) == proof["providers"] == count
                and providers["libllama.so.0"].parent.name == name
                and proof["image_sha256"] == record["image_sha256"]
                and record["abi"] == b["original_abi"],
                "ABI and real relocation " + key,
            )
            rows[key] = count
        arms[name] = dict(image_sha256=record["image_sha256"], providers=rows)
    return dict(
        status=b["status"],
        model_starts=0,
        server_starts=0,
        old_relink_status=a["status"],
        first_receipt_sha256=B["FIRST_LINK"],
        current_receipt_sha256=CURRENT,
        source_commits=[a["commit"], b["commit"]],
        link_comparison=b["arms"]["RELINK"]["link_comparison"],
        common_compiler_headers=len(common),
        objects=166,
        common_other_objects=165,
        exported_symbols=b["original_abi"]["exports"],
        arms=arms,
        historical_pack_sha256=B["PACK"],
        first_wall_s=a["wall_s"],
        current_wall_s=b["wall_s"],
        current_build_bytes=b["build_output_bytes"],
        server_sources=b["server_sources"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.first, args.second), sort_keys=True, indent=2, allow_nan=False))
