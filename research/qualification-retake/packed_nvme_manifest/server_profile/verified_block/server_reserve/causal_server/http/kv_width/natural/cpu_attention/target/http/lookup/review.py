"""Reopen the rejected build, both native images and all dispatcher results."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(str(HERE / "run.py"))
G, need, sha, save = (M[k] for k in ("G", "need", "sha", "save"))
PINS = (
    "b5db5086652745d9918fb7160f872460be04d1a70450001325170acb98b19d7a",
    "f0ad5c5216c8001fe717431c6056aca42e43459b3685bb209c0e1e2bfd312124",
    "20d24f1d0edb935f1afd60a40568590dc6eb440e404de857a0630dfd8f11b073",
)


def review(roots):
    fail, one, two = (
        G["read"](root / "result.json", pin) for root, pin in zip(roots, PINS, strict=True)
    )
    need(
        fail["status"] == "FAIL_PRESERVED"
        and "patch" in fail["error"]
        and "FAILED" in (roots[0] / "FILTER/patch.log").read_text(),
        "preserved R01",
    )
    first = {k: v for k, v in one.items() if k != "wall_s"}
    need(
        first == {k: v for k, v in two.items() if k != "wall_s"}
        and first["status"] == "GO_NATIVE_CONTEXT_FILTER_ONLY",
        "independent compilation and C++ dispatch",
    )
    for root, r in zip(roots[1:], (one, two), strict=True):
        for name, image in r["images"].items():
            need(
                sha(root / name / "libllama-common.so.0") == image["ELF_sha256"]
                and sha(root / name / "ngram-map.cpp.o") == image["object_sha256"]
                and sha(root / name / "common/ngram-map.cpp") == image["source_sha256"],
                "native image",
            )
        for name, digest in r["raw_digests"].items():
            raw = G["read"](root / name / "proposals.json", digest)
            for case, actions in raw.items():
                indices = [a["at"] for a in actions if a["proposal"]]
                need(
                    indices == r["arms"][name][case]["positions"]
                    and sum(x["emitted"] for x in actions) + 1
                    == r["arms"][name][case]["target_count"],
                    "real raw rows",
                )
        need(
            sha(root / "historic/proposals.json") == r["historical_rows_sha256"]
            and sha(root / "server-plan") == r["dispatcher_sha256"],
            "original control",
        )
    return first | dict(
        input_sha256=list(PINS),
        replica_wall_s=[one["wall_s"], two["wall_s"]],
        preserved_fail_wall_s=fail["wall_s"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("failed", "first", "second", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = review((a.failed, a.first, a.second))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result = dict(status="FAIL_PRESERVED", error=str(exc))
    save(a.new_output_dir / "result.json", result)
    print(result["status"])
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
