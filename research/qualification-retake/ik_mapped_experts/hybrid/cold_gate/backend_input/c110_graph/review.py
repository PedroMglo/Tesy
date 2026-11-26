"""Reopen the two 120B C110 forward cuts and identify the physical source for all bank copies."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "grade.py"))
A, FR, G, need = (C[k] for k in ("A", "FR", "G", "need"))
PHASE = run_path(str(C["HYBRID"] / "driver_62073/review_real.py"))["phase_report"]


def review(a):
    r = A["receipt"](a.family / "receipt.json", a.family_sha256)
    need(
        r["status"] == "PASS_C110_BANK_INPUT_NUMERIC"
        and r["model_starts"] == 4
        and r["swap_peak"] == 0
        and set(r["arms"]) == set(C["SOURCES"]),
        "incomplete family",
    )
    state = r["authority"]
    profile = state["profile"]
    need(
        A["sha"](a.plan) == profile["plan_sha256"] == A["PLAN"]
        and A["DEV"]["IO"].stat_id(a.model) == profile["model_stat"],
        "model stat/plan",
    )
    on, schedules = C["history"](a.previous, a.plan)
    refs = FR["OPS"]["CUT"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    results = {}
    for label in C["SOURCES"]:
        path = a.family / label
        arm = A["receipt"](path / "receipt.json", r["arms"][label]["receipt_sha256"])
        need(
            FR["inventory"](path) == arm["raw_sha256"]
            and arm["model_starts"] == 1
            and arm["returncode"] == arm["swap_peak"] == 0
            and arm["restored"]
            and arm["child_gone"],
            "incomplete arm/drift",
        )
        grade = C["evaluate"](label, path, a.previous, a.model, a.plan, on, schedules, refs)
        need(all(json.loads(json.dumps(v)) == arm[k] for k, v in grade.items()), "different grade")
        phases = PHASE(path, arm, grade["grade"])
        results[label] = dict(
            **phases,
            physical=grade["physical"],
            equal_finite_F32=402176,
            independent_max_abs={
                name: {p: v["max_abs"] for p, v in rows.items()}
                for name, rows in grade["independent_references"].items()
            },
            independent_argmax={
                name: [v["unique_greedy_equal"] for v in rows.values()]
                for name, rows in grade["independent_references"].items()
            },
            c118_samples=arm["c118"]["sample_count"],
        )
    return dict(
        decision="GO_CONTROLLED_C110_COST",
        evidence="MEDIDO",
        commit=profile["commit"],
        tree=profile["tree"],
        model_sha256=profile["model_sha256"],
        build_sha256=state["build_sha256"],
        historical_sha256=C["HISTORY"],
        tiny_gate_sha256=state["tiny_input_sha256"],
        c55_sha256=profile["c55_sha256"],
        family_sha256=a.family_sha256,
        model_starts=4,
        forwards=8,
        http_requests=0,
        energy_j=None,
        swaps_B=0,
        arms=results,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "family",
        "previous",
        "model",
        "plan",
        "c110-parent",
        "stock-file",
        "cpu-d0",
        "cpu-d1",
        "new-output-dir",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    (a.new_output_dir / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["decision"])
