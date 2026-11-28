"""Price the joint change against exactly the same two-region service schedule."""

import argparse
import hashlib
import json
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FR = run_path(HERE / "frontier.py")
PR = run_path(HERE / "service_price.py")
L, need, sha = (FR[k] for k in ("L", "need", "sha"))
METHOD = "531ea29986305817d2fd88336d1e4be1d9727b941e7fdd0f181e10528c38da7f"
PARENT = "057171001dbdfaebeed7fca2609acca2bfd0c3cac3f2f1e0babbd4e75d70ad3e"


def digest(value):
    data = json.dumps(value, separators=(",", ":")) + "\n"
    return hashlib.sha256(data.encode()).hexdigest()


def study(calls, identities, selected, exterior, parent):
    def clocks(mode, saving, concrete):
        times = exterior.copy()
        schedule = []
        for num, groups in calls.items():
            puts, releases = {}, {}
            for group in groups:
                for j in group:
                    layer, expert = identities[j.order]
                    puts[j.order] = (
                        (j.put * (1_000_000 - saving) + 999_999) // 1_000_000
                        if layer < 25
                        else j.put
                    )
                    releases[j.order] = (
                        max(0, j.group - 2)
                        if mode == "two"
                        else (0 if expert in selected[layer] else j.group)
                    )
            if concrete:
                assigned = [
                    [L["Job"](j.order, j.group, j.read, max(1, puts[j.order])) for j in g]
                    for g in groups
                ]
                end, _, events = FR["schedule"](assigned, 2)
                schedule.append(events)
            else:
                end = FR["lower"](groups, releases, puts)
            if num <= 46:
                times["first_final"] += end
            if num >= 3:
                times["decode"] += end
        return times, digest(schedule) if concrete else None

    @cache
    def floor(saving):
        return clocks("two", saving, False)[0]

    control, ref = clocks("two", 0, True)
    need(
        control == parent["clocks_ns"]["two_schedule"]
        and ref == parent["schedule_sha256"]
        and floor(0) == parent["clocks_ns"]["two"]
        and clocks("t1", 0, False)[0] == parent["clocks_ns"]["t1_four"],
        "sealed independent controls",
    )
    result = PR["threshold"](floor)
    result["min_cpu_set_reduction_ppm"] = result.pop("min_read_reduction_ppm")
    if "free_read_floor_ns" in result:
        result["free_cpu_set_floor_ns"] = result.pop("free_read_floor_ns")
    concrete, trace = clocks("two", 1_000_000, True)
    t1 = clocks("t1", 1_000_000, False)[0]
    limits = L["LIMITS"]
    maximum = {k: val - concrete[k] for k, val in limits.items()}
    need(all(floor(1_000_000)[k] <= v for k, v in concrete.items()), "ideal exceeds witness")
    return dict(
        original_schedule_sha256=ref,
        schedule_sha256=trace,
        threshold=result,
        free_cpu_set_floor_ns=floor(1_000_000),
        near_free_cpu_set_schedule_ns=concrete,
        maximum_extra_schedule_ns=maximum,
        four_t1_free_cpu_set_floor_ns=t1,
        decision="NO_GO"
        if any(floor(1_000_000)[k] > lim for k, lim in limits.items())
        else "GO_TEMPORAL_FIXTURE_ONLY"
        if min(maximum.values()) >= 0
        else "INCONCLUSIVE_SCHEDULE",
    )


def run(archive, plan_path):
    parent_path = HERE / "frontier.json"
    parent = json.loads(parent_path.read_bytes())
    need(
        sha(HERE / "composition.md") == METHOD
        and sha(parent_path) == PARENT
        and sha(plan_path) == parent["plan_sha256"],
        "combined intervention or plan seal",
    )
    screen = run_path(HERE.parents[1] / "screen.py")
    src = screen["SOURCE"]
    dead = run_path(screen["HERE"] / "renewal/deadlines.py")
    plan = FR["train"](screen, archive)
    need(json.loads(plan_path.read_bytes()) == plan, "confirmed T1-only selection")
    old = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    result = {}
    for label, prev in parent["traces"].items():
        _, auth = screen["read_arm"](archive, label, old[label])
        name, seal, _ = src["SOURCES"][label]
        folder = archive / ("part-" + label[1:]) / name
        if label == "P97":
            rows, _ = src["T"]["PFJ"]["read_journal"](folder / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = src["Q"]["read_new"](folder, seal)
        ids = [(e.layer, e.expert) for e in rows if e.kind == 11]
        need(
            auth["journal_sha256"] == prev["journal_sha256"] and len(ids) == 2354,
            "original jobs and journal",
        )
        result[label] = study(
            L["region_jobs"](rows, src, dead), ids, plan["ranked"], auth["outside_calls_ns"], prev
        )
    verdicts = {v["decision"] for v in result.values()}
    verdict = (
        "NO_GO"
        if "NO_GO" in verdicts
        else "GO_TEMPORAL_FIXTURE_ONLY"
        if verdicts == {"GO_TEMPORAL_FIXTURE_ONLY"}
        else "INCONCLUSIVE_SCHEDULE"
    )
    return dict(
        classification="SIMULATED_ORACLE",
        decision=verdict,
        traces=result,
        parent_sha256=PARENT,
        protocol_sha256=METHOD,
        source_sha256=sha(Path(__file__)),
        model_loads=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("archive", "plan", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        record = run(a.archive, a.plan)
    except Exception as exc:
        record = dict(
            classification="NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            reason=str(exc),
        )
    temp = a.new_output_dir / ".result.tmp"
    with temp.open("x") as f:
        json.dump(record, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    temp.rename(a.new_output_dir / "composition.json")
    print(record["classification"], record.get("decision", record.get("reason", "")))
    raise SystemExit(record["classification"] != "SIMULATED_ORACLE")
