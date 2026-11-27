"""Reproduce the two-case decision from public metrics or from the original native captures."""

import argparse
import hashlib
import json
import math
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
METRICS = ("prefix_s", "prefill153_s", "decode32_s", "total_s")
CASES = ("code153", "nominal153")
PAIRS = ((0, 1, 2, 3), (7, 6, 5, 4))
ELF = {
    "R": "e64dda51f4e6d2b8bd43ee6c52a7db2367c263ae16ed1fe48b7cb99e6028d56e",
    "G": "819a116fe31b0dddb24988ad8364f9a24970f99c447f48c31cdebdc399d84c05",
}
CPU = {
    "R": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "G": "31f5c0ab3584a0c263091f1e5e45e5340cf63f5b853cc08e2ead6b01011ee41f",
}
EVALUATOR = "906709a2022dbf5e913245ddfe68c575fa84d11f4c17df2e34219d9f11323b2c"
FIXTURE = (
    ROOT / "results/c276-post-c274-r2-causal-qualification-20261005T204839Z/development-inputs.json"
)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def check_cases(cases):
    need(set(cases) == set(CASES), "both workloads required")
    for case, family in cases.items():
        rows = family["arms"]
        need(
            len(rows) == 8
            and [a["name"] for a in rows] == [str(i) + r for i, r in enumerate("RGPWWPGR", 1)],
            "fixed independent processes and order",
        )
        ref = rows[0]
        for a in rows:
            role = a["role"]
            image = "R" if role == "R" else "G"
            need(
                a["case"] == case
                and a["name"].endswith(role)
                and a["states"] == ref["states"]
                and a["logical_loads"] == ref["logical_loads"]
                and a["full_logits_sha256"] == ref["full_logits_sha256"]
                and len(a["states"]) == 2
                and a["binary_sha256"] == ELF[image]
                and a["cpu_sha256"] == CPU[image],
                "native identities, model outputs, pool state or work",
            )
            need(
                (a["pack_fd_samples"] > 0) == (role in "PW")
                and a["maxima"]["direct_model_fds"] > 0
                and a["maxima"]["swap_bytes"] == 0
                and a["live_samples"] > 0
                and a["c118"]["s"] >= 60
                and 0 <= a["c55_age_s"] < 3600,
                "transport, admission or native process",
            )
            m = a["metrics"]
            need(
                set(m) == set(METRICS)
                and all(math.isfinite(v) and v > 0 for v in m.values())
                and math.isclose(
                    m["total_s"], m["prefill153_s"] + m["decode32_s"], rel_tol=0, abs_tol=1e-8
                ),
                "finite native phase clocks",
            )
            if role in "PW":
                need(
                    a["store_loads"] > 0 and a["store_weight_bytes"] == a["store_loads"] * 13219200,
                    "completed pack load accounting",
                )
            elif role == "G":
                need(a["store_loads"] == a["store_weight_bytes"] == 0, "GGUF control")
            else:
                need(a["store_loads"] is a["store_weight_bytes"] is None, "original C269 control")
        need(len({a["unit"] for a in rows}) == 8, "reused process identity")


def compare(cases, left, right):
    contrasts = {}
    for case, family in cases.items():
        pairs = []
        for block in PAIRS:
            roles = {family["arms"][i]["role"]: family["arms"][i] for i in block}
            a, b = roles[left], roles[right]
            gain = {k: 100 * (a["metrics"][k] - b["metrics"][k]) / a["metrics"][k] for k in METRICS}
            pairs.append(dict(control=a["name"], candidate=b["name"], gain_percent=gain))
        contrasts[case] = dict(
            pairs=pairs,
            median_paired_gain_percent={
                k: median(p["gain_percent"][k] for p in pairs) for k in METRICS
            },
        )
    qualified, phases, component = [], [], []
    for case in CASES:
        data = contrasts[case]
        m = data["median_paired_gain_percent"]
        other = next(c for c in CASES if c != case)
        guard = contrasts[other]["median_paired_gain_percent"]["total_s"] >= -5
        positive = {k: all(p["gain_percent"][k] > 0 for p in data["pairs"]) for k in METRICS}
        if guard and (
            (m["total_s"] >= 8 and positive["total_s"])
            or (m["decode32_s"] >= 15 and positive["decode32_s"] and m["total_s"] > 0)
        ):
            qualified.append(case)
        for phase, protect in (("prefill153_s", "decode32_s"), ("decode32_s", "prefill153_s")):
            if (
                guard
                and m[phase] >= 10
                and positive[phase]
                and m["total_s"] > 0
                and m[protect] >= -5
            ):
                phases.append(dict(case=case, phase=phase))
        if guard and positive["prefill153_s"] and m["decode32_s"] >= -5 and m["total_s"] > 0:
            component.append(case)
    return dict(
        cases=contrasts,
        global_cases=qualified,
        phase_survivors=phases,
        positive_prefill_component_cases=component,
    )


def decide(cases):
    check_cases(cases)
    comparisons = {
        a + "/" + b: compare(cases, a, b)
        for a, b in (("R", "W"), ("G", "W"), ("G", "P"), ("P", "W"), ("R", "G"))
    }
    accepted = sorted(
        set(comparisons["R/W"]["global_cases"]) & set(comparisons["G/W"]["global_cases"])
    )
    return dict(
        status="GO_SUPPLIED_COMBINATION" if accepted else "NO_GO_SUPPLIED_COMBINATION",
        qualified_cases=accepted,
        comparisons=comparisons,
        backend="NO_GO_FULL_REWRITE_FOR_THESE_MECHANISMS",
        m3="PARTIAL",
        m4="NOT_MET",
    )


def reopen(physical, window, case, program):
    r = read(physical / "receipt.json")
    need(
        r["status"] == "COMPLETE_SUPPLIED_CASE"
        and r["case"] == case
        and r["protocol_sha256"] == sha(HERE / "protocol.md")
        and r["window_sha256"] == sha(window / "receipt.json")
        and r["input_sha256"] == sha(FIXTURE),
        "sealed family or fixture",
    )
    spec = read(program["C293"] / "protocol.json")
    original = program["C280"] / "compact.json"
    need(sha(original) == program["ORIGINAL"], "independent C280 work")
    controls = [a for a in read(original)["arms"] if a["case"] == case and a["profile"] == "R0"]
    need(
        len(controls) == 2
        and controls[0]["logical_load_generations"] == controls[1]["logical_load_generations"],
        "independent original loads",
    )
    win = read(window / "receipt.json")
    native = {}
    for row in r["arms"]:
        folder = physical / row["name"]
        unit, role = row["unit"], row["role"]
        raw = folder / "raw"
        cap = raw / (unit + ".native")
        argv = read(folder / "argv-supplied.json")
        mon, launch = (read(raw / (unit + suffix)) for suffix in (".json", ".launch.json"))
        manifest = argv["expected"].get(program["live"].STORE_ENV)
        m = program["grade"](
            cap,
            FIXTURE,
            case,
            role,
            spec["expected_full_logits_sha256"][case],
            controls[0]["logical_load_generations"],
            manifest,
        )
        need(all(row[k] == v for k, v in m.items()), "reopened native output")
        need(
            row == read(folder / "checked.json")
            and row["energy"] == program["power"](folder, row)
            and sha(raw / (unit + ".json")) == row["monitor_sha256"]
            and sha(cap / "result.json") == row["native_sha256"]
            and sha(folder / "argv-supplied.json") == row["argv_sha256"]
            and mon["explicit_env"] == argv["expected"]
            and mon["maxima"] == row["maxima"]
            and mon["returncode"] == 0
            and mon["stop_reason"] is None
            and mon["process_identity"] == launch["process_identity"]
            and sha(folder / "resource-supplied.json") == launch["resource_protocol_sha256"]
            and mon["limits"]["resource_protocol_sha256"] == launch["resource_protocol_sha256"],
            "raw resource receipts",
        )
        inv = program["PK"]["PK"]["compact"].validate_inventory(
            folder, unit, {"native_explicit_env": argv["expected"]}, launch
        )
        need(inv == row["c118"], "reopened C118")
        native[row["name"]] = read(cap / "result.json")
    keep = (
        "cpu",
        "gpu_name",
        "gpu_driver",
        "gpu_total_mib",
        "model_device",
        "model_fs",
        "canonical_memory",
        "power",
        "span_s",
        "reason",
    )
    return dict(
        arms=r["arms"],
        receipt_sha256=sha(physical / "receipt.json"),
        commit=r["commit"],
        tree=r["tree"],
        runner_sha256=r["runner_sha256"],
        window_sha256=r["window_sha256"],
        window={k: win[k] for k in keep},
        elapsed_s=r["elapsed_s"],
    ), native


def build(locations):
    prog = run_path(HERE / "run.py")
    need(sha(ROOT / "tools/expert_store_cost_gate.py") == EVALUATOR, "original evaluator")
    data, truth = {}, {}
    for case in CASES:
        folder, window = locations[case]
        data[case], truth[case] = reopen(folder, window, case, prog)
    decision = decide(data)
    official = {}
    for r in "PW":
        names = ["2G", "3P", "6P", "7G"] if r == "P" else ["2G", "4W", "5W", "7G"]
        test = prog["cost"].evaluate({c: [t[n] for n in names] for c, t in truth.items()})
        own = decision["comparisons"]["G/" + r]
        need(
            set(test["global_qualified_cases"]) == set(own["global_cases"])
            and sorted(test["phase_survivor"], key=lambda p: (p["case"], p["phase"]))
            == sorted(own["phase_survivors"], key=lambda p: (p["case"], p["phase"])),
            "official gates",
        )
        for c in CASES:
            ref, ours = test["cases"][c], own["cases"][c]
            need(
                ref["median_paired_gain_percent"] == ours["median_paired_gain_percent"]
                and [p["gain_percent"] for p in ref["pairs"]]
                == [p["gain_percent"] for p in ours["pairs"]],
                "official paired clocks",
            )
        official["G/" + r] = test["status"]
    return dict(
        schema="tesy-supplied-wave-decision-v1",
        protocol_sha256=sha(HERE / "protocol.md"),
        official_evaluator_sha256=EVALUATOR,
        official_status=official,
        cases=data,
        decision=decision,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", type=Path)
    p.add_argument("--code", type=Path)
    p.add_argument("--nominal", type=Path)
    p.add_argument("--code-window", type=Path)
    p.add_argument("--nominal-window", type=Path)
    p.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    if a.check:
        report = read(a.check)
        need(
            report["decision"] == decide(report["cases"])
            and report["protocol_sha256"] == sha(HERE / "protocol.md")
            and report["official_evaluator_sha256"]
            == sha(ROOT / "tools/expert_store_cost_gate.py")
            == EVALUATOR,
            "public result",
        )
    else:
        if not all((a.code, a.nominal, a.code_window, a.nominal_window, a.new_output_dir)):
            p.error("raw mode requires both cases, their windows and an exclusive output directory")
        a.new_output_dir.mkdir()
        try:
            report = build(
                {"code153": (a.code, a.code_window), "nominal153": (a.nominal, a.nominal_window)}
            )
        except Exception as exc:
            with (a.new_output_dir / "failure.json").open("x") as f:
                json.dump(dict(status="FAIL_PRESERVED", reason=str(exc)), f)
            raise
        with (a.new_output_dir / "decision.json").open("x") as f:
            json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
            f.write("\n")
    print(report["decision"]["status"])
