"""Reopen both physical orders and the independent numerical service trace."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE / "grade.py"))
R = run_path(str(HERE.parent / "review.py"))
FR, A, need = (G[k] for k in ("FR", "A", "need"))


def review(family, digest, numerical):
    r = A["receipt"](family / "receipt.json", digest)
    need(
        r["status"] == "PASS_C110_MATCHED_PRICE"
        and r["model_starts"] == 4
        and r["swap_peak"] == 0
        and set(r["arms"]) == set(G["ORDER"])
        and r["authority"]["numerical_sha256"] == G["FAMILY"],
        "incomplete cost family",
    )
    gold = G["reference"](numerical)
    arms = {}
    for label in G["ORDER"]:
        p = family / label
        arm = A["receipt"](p / "receipt.json", r["arms"][label]["receipt_sha256"])
        need(
            arm["raw_sha256"] == FR["inventory"](p)
            and arm["model_starts"] == 1
            and arm["returncode"] == arm["swap_peak"] == 0
            and arm["restored"]
            and arm["child_gone"],
            "raw drift or incomplete exit",
        )
        grade = G["grade"](label, p, gold)
        need(all(arm[k] == v for k, v in grade.items()), "grade changed")
        phases = R["PHASE"](
            p,
            arm,
            {
                "source_and_slot": {
                    "matrix_requests_B": {"prefill": 14752627200, "teacher": 1692057600}
                }
            },
        )
        for phase, ack in (
            ("prefill", phases["phases"]["prefill"]["ack_interval_s"]),
            ("teacher", phases["phases"]["teacher"]["ack_interval_s"]),
            ("cleanup", phases["cleanup_ack_s"]),
        ):
            need(
                grade["native_ns"][phase] / 1e9 <= ack + 0.001,
                "native exceeds surrounding interval",
            )
        arms[label] = dict(**grade, **phases, c118_samples=arm["c118"]["sample_count"])
    result = G["compare"](arms)
    need(all(r[k] == v for k, v in result.items()), "pair decision changed")
    state = r["authority"]
    return dict(
        **result,
        arms=arms,
        commit=state["profile"]["commit"],
        tree=state["profile"]["tree"],
        model_sha256=state["profile"]["model_sha256"],
        build_sha256=state["cost_build_sha256"],
        c55_sha256=state["profile"]["c55_sha256"],
        family_sha256=digest,
        numerical_sha256=G["FAMILY"],
        model_starts=4,
        forwards=8,
        http_requests=0,
        energy_j=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "numerical", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a.family, a.family_sha256, a.numerical)
    (a.new_output_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(result["decision"])
