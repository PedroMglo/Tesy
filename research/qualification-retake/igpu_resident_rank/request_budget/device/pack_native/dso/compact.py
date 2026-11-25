"""Recheck the archived C291 link outcomes without loading either private library."""

import argparse
import hashlib
import json
from pathlib import Path

PINS = (
    "6526d401ab30ee3db1f72c23608eb2f0987a385c3be295b3aa4967b7fbf360c4",
    "cfd616fda7fcdac7aaf6774f9b6d2aac7ea5186a5629fa33eb1bff58a00b34c8",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(ok, label):
    if not ok:
        raise ValueError(label)


def compact(early, current):
    rows = []
    for src, pin in zip((early, current), PINS, strict=True):
        receipt = src / "receipt.json"
        check(sha(receipt) == pin, "terminal identity")
        rows.append(json.loads(receipt.read_bytes()))
    x, y = rows
    check(
        x["status"] == "FAIL_PRESERVED" and y["status"] == "PASS_C291_PACK_PFJ_DSO_STATIC_C281",
        "outcomes",
    )
    for folder in (early, current):
        check(
            sha(folder / "intact/libllama.so.0.0.9884")
            == y["intact_sha256"]
            == x["mismatch"]["actual_sha256"],
            "intact file",
        )
    for name in ("candidate", "control"):
        check(sha(current / y[name + "_file"]) == y[name + "_sha256"], name + " file")
    for role, row in y["object_comparisons"].items():
        check(
            sha(current / "gold" / (role + ".o")) == row["actual"]
            and sha(current / "gold" / (role + ".sections.json")) == row["report_sha256"],
            "gold TU",
        )
    check(
        sha(current / "gold/elf.sections.json") == y["control_section_delta_sha256"],
        "changed gold sections",
    )
    census = {}
    for group, count in (
        ("queries", 53),
        ("control_queries", 9),
        ("capture_queries", 2),
        ("control_capture_queries", 2),
    ):
        check(len(y[group]) == count, group)
        for label, q in y[group].items():
            check(q["returncode"] == 0, "loader return")
            for ext, field in ((".out", "stdout_sha256"), (".err", "stderr_sha256")):
                check(sha(current / "loader" / (label + ext)) == q[field], label + ext)
        census[group] = count
    for ref, other, count in (
        ("startup", "control_startup", 24),
        ("capture_startup", "control_capture_startup", 18),
    ):
        before, after = y[ref], y[other]
        check(
            len(before) == count
            and before.keys() == after.keys()
            and {k for k in before if before[k] != after[k]} == {"libllama.so.0"},
            ref,
        )
    return dict(
        status=y["status"],
        receipt_sha256={"R01": PINS[0], "R02": PINS[1]},
        R01=dict(
            status=x["status"],
            stage=x["stage"],
            elapsed_s=x["elapsed_s"],
            scope_peak_bytes=x["final_scope"]["memory.peak"],
            original_bytes=x["mismatch"]["original_bytes"],
            intact_bytes=x["mismatch"]["actual_bytes"],
            changed_sections=sorted(x["mismatch"]["sections"]),
        ),
        R02={
            k: y[k]
            for k in (
                "commit",
                "tree",
                "original_sha256",
                "intact_sha256",
                "control_sha256",
                "candidate_sha256",
                "build_variant",
                "control_exec_same",
                "control_alloc_differences",
                "control_section_delta_sha256",
                "inputs_sha256",
                "patch_sha256",
                "header_sha256",
                "static_preflight_sha256",
                "c281_closure_sha256",
                "c292_closure_sha256",
                "control_export_changes",
                "candidate_export_changes_vs_control",
                "consumers",
                "elapsed_s",
                "final_scope",
                "server_starts",
                "model_forwards",
            )
        },
        loader_queries=census,
        verified_logs=132,
        C281_providers=24,
        C292_providers=18,
        required_next="numerical control and candidate",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("r01", type=Path)
    ap.add_argument("r02", type=Path)
    args = ap.parse_args()
    print(json.dumps(compact(args.r01, args.r02), indent=2, sort_keys=True))
