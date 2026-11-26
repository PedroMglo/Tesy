"""Reopen the native two-arm qualification with the sealed C110 rows and the saved maps."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE / "grade.py"))
R = run_path(str(HERE.parents[2] / "c110_graph/review.py"))
A, FR, need = C["A"], C["FR"], C["need"]


def review(a):
    family = A["receipt"](a.family / "receipt.json", a.family_sha256)
    state = family["authority"]
    p = state["profile"]
    need(
        family["status"] == "PASS_NATIVE_C110"
        and family["model_starts"] == 2
        and family["swap_peak"] == 0
        and set(family["arms"]) == set(C["MODES"])
        and A["sha"](a.plan) == p["plan_sha256"] == A["PLAN"]
        and A["DEV"]["IO"].stat_id(a.model) == p["model_stat"],
        "native family or model identity",
    )
    on, schedules = C["C"]["history"](a.previous, a.plan)
    refs = FR["OPS"]["CUT"]["references"](a.c110_parent, a.stock_file, a.cpu_d0, a.cpu_d1)
    gold = C["reference"](a.numerical, a.plan)
    results = {}
    for mode in C["MODES"]:
        path = a.family / mode
        arm = A["receipt"](path / "receipt.json", family["arms"][mode]["receipt_sha256"])
        need(
            FR["inventory"](path) == arm["raw_sha256"]
            and arm["returncode"] == arm["swap_peak"] == 0
            and arm["restored"]
            and arm["child_gone"]
            and arm["model_starts"] == 1,
            "arm lifecycle",
        )
        for phase in ("L", "C", "P", "T", "F"):
            dll = [v for v in arm["live_providers"][phase] if Path(v).name == "libllama.so"]
            need(
                len(dll) == 1
                and state["providers"][dll[0]]["sha256"] == state["candidate_library_sha256"],
                "original ELF loaded wrong backend",
            )
        grade = C["evaluate"](mode, path, a.previous, a.model, a.plan, on, schedules, refs, gold)
        need(
            all(json.loads(json.dumps(v)) == arm[k] for k, v in grade.items()), "different regrade"
        )
        contrasts = {
            k: {
                pos: dict(max_abs=v["max_abs"], greedy_equal=v["unique_greedy_equal"])
                for pos, v in rows.items()
            }
            for k, rows in grade["independent_references"].items()
        }
        results[mode] = R["PHASE"](path, arm, grade["grade"]) | dict(
            physical=grade["physical"],
            ordered_quartets=grade["ordered_quartets"],
            phase_payload_B=grade["phase_bytes"],
            last_generation_sets=grade["sets_in_final_generation"],
            equal_finite_F32=402176,
            logits_sha256=grade["logits_sha256"],
            independent=contrasts,
            c118_samples=arm["c118"]["sample_count"],
        )
    return dict(
        decision="GO_SERVER_CONVERSATION_GATE",
        evidence="MEDIDO",
        commit=p["commit"],
        tree=p["tree"],
        family_sha256=a.family_sha256,
        model_sha256=p["model_sha256"],
        native_library_sha256=state["candidate_library_sha256"],
        c55_sha256=p["c55_sha256"],
        build_sha256=state["build_sha256"],
        tiny_sha256=state["tiny_sha256"],
        arms=results,
        model_starts=2,
        forwards=4,
        http_requests=0,
        energy_J=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "family",
        "previous",
        "model",
        "plan",
        "numerical",
        "c110-parent",
        "stock-file",
        "cpu-d0",
        "cpu-d1",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    r = review(a)
    (a.new_output_dir / "result.json").write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(r["decision"])
