"""Compare the three graded arms without publishing the private HTTP streams."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
family = run_path(HERE / "family.py")
need, sha, save = family["need"], family["sha"], family["save"]
TIMES = ("first_final_s", "transport_complete_s", "validated_terminal_s", "prefill_s", "decode_s")


def compare(first, second):
    result = {}
    for i, (a, b) in enumerate(zip(first["rows"], second["rows"], strict=True), 1):
        row = {}
        for name in TIMES:
            need(a[name] > 0 and b[name] > 0, "timing denominator")
            row[name] = dict(seconds_saved=a[name] - b[name], fraction_saved=1 - b[name] / a[name])
        row["decode_tok_s_delta"] = b["decode_tok_s"] - a["decode_tok_s"]
        result[f"T{i}"] = row
    return result


def extract(root, history):
    metadata = json.loads((root / "family.json").read_bytes())
    need(metadata["status"] == family["DONE"], "incomplete family")
    review = run_path(HERE / "review.py")
    arms = {}
    for mode in family["ORDERS"]:
        directory = root / mode
        source = directory / "arm.json"
        row = json.loads(source.read_bytes())
        need(
            sha(source) == metadata["arms"][mode]["sha256"] and row["mode"] == mode,
            "private arm or order changed",
        )
        receipt = directory / "receipt.json"
        need(sha(receipt) == row["receipt_sha256"], "native arm changed")
        native = json.loads(receipt.read_bytes())
        grade = review["grade_arm"](directory, native, history)
        need(grade == row["grade"], "grade not reproduced")
        arms[mode] = grade
    return dict(
        status="REPRODUCED_NOMINAL_TRANSPORT_BLOCK",
        arms=arms,
        differences={
            left + "_" + right: compare(arms[left], arms[right])
            for left, right in (("R", "O"), ("O", "P"), ("R", "P"))
        },
        nominal_targets={
            mode: dict(
                first_final_le_10=row["rows"][1]["first_final_s"] <= 10,
                decode_ge_6=row["rows"][1]["decode_tok_s"] >= 6,
            )
            for mode, row in arms.items()
        },
        repeats_per_arm=1,
        natural_requests=6,
        model_processes=3,
        family_elapsed_s=metadata["family_elapsed_s"],
        family_sha256=sha(root / "family.json"),
        commit=metadata["identity"]["commit"],
        tree=metadata["identity"]["tree"],
        program_sha256=sha(Path(__file__)),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("raw", "history-dir", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = extract(a.raw, a.history_dir)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    save(a.new_output_dir / "receipt.json", result)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
