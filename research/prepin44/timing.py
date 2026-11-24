"""Optimistic chronology of the changed admission stream in one C163 prefill arm."""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

UNIT = Path(__file__).resolve().parent
ROOT = UNIT.parents[1]
sys.path[:0] = [str(UNIT), str(ROOT / "research/prefill44-replay"), str(ROOT / "tools")]
from policy import Fixture  # noqa: E402
from replay import need, replay  # noqa: E402
from study import C163, inputs, sha  # noqa: E402


def lower_bound(times, fixed, jobs):
    """Each job and the load of every contained interval constrain its duration."""
    ending = defaultdict(list)
    for r, d, duration in jobs:
        need(0 <= r < d < len(times) and duration >= 0, "invalid job window")
        ending[d].append((r, duration))
    wall = [0] * len(times)
    expired = Counter()
    for k in range(1, len(times)):
        need(times[k] >= times[k - 1], "unordered protected clock")
        wall[k] = wall[k - 1] + fixed[k - 1]
        for start, duration in ending[k]:
            wall[k] = max(wall[k], wall[start] + duration)
            expired[start] += duration
        if ending[k]:
            total = 0
            for start in sorted(expired, reverse=True):
                total += expired[start]
                wall[k] = max(wall[k], wall[start] + total // 4)
    need(wall[-1] <= times[-1] - times[0] + 1, "historical clock violates a retained constraint")
    return wall[-1]


def stages(rows, routing):
    begins = {r["transition_seq"]: r for r in routing if r["call_id"] in (9, 10)}
    visits, metadata = Counter(), {}
    group = None
    markers, load_spans = defaultdict(list), {}
    calls = {}
    admissions = []
    demand_order = defaultdict(list)
    for r in rows:
        call, layer, seq, kind = (r[n] for n in ("call_id", "layer", "seq", "kind"))
        if call not in (9, 10):
            continue
        if seq in begins:
            route = begins[seq]
            tile = 4 if (call, layer) == (10, 35) else visits[call, layer]
            visits[call, layer] += 1
            group = call, tile, layer, 0 if route["mode"] else -1
        if kind in ("CALL_BEGIN", "CALL_END"):
            markers[call].append(r)
            calls[call, kind] = r["mono_us"]
        if kind == "DEMAND":
            need(
                group is not None and (group[0], group[2], group[3]) == (call, layer, r["wave"]),
                "demand geometry",
            )
            demand_order[group].append(r["expert"])
            if "first" not in metadata.setdefault(group, {}):
                metadata[group]["first"] = seq
                markers[call].append(r)
        if kind in ("WAIT_BEGIN", "WAIT_END", "WAVE_DONE", "REMAP_DONE"):
            markers[call].append(r)
            if kind.endswith("_DONE"):
                need(
                    group is not None
                    and (group[0], group[2], group[3]) == (call, layer, r["wave"]),
                    "wave end geometry",
                )
                metadata.setdefault(group, {})["done"] = seq
                group = (*group[:3], group[3] + 1)
        if kind in ("RESERVE", "LOAD_BEGIN", "LOAD_END"):
            key = tuple(r[k] for k in ("call_id", "layer", "expert", "slot", "generation"))
            if kind == "RESERVE":
                admissions.append(key)
            elif kind == "LOAD_BEGIN":
                need(key not in load_spans, "duplicate generation")
                load_spans[key] = [r["mono_us"]]
            else:
                load_spans[key].append(r["mono_us"])
    need(len(admissions) == len(set(admissions)) == len(load_spans), "load conservation")
    return markers, calls, metadata, load_spans, admissions, demand_order


def arm_report(rows, routing, control, candidate, *, capture_windows=None):
    markers, calls, metadata, service, admissions, demand_order = stages(rows, routing)
    need(control.reservations == admissions, "control and journal physical reservations differ")
    logical = control.admission_context
    target = Counter(candidate.admission_context)
    need(len(logical) == len(admissions), "incomplete admission labels")
    retained = Counter(logical) & target
    # The trace and both fixtures have at most one job for an expert at this
    # release and role. Duplicate jobs need an explicit occurrence join.
    need(max(Counter(logical).values()) == max(target.values()) == 1, "ambiguous job occurrence")
    calls_report = {}
    for call in (9, 10):
        m = markers[call]
        t = [r["mono_us"] for r in m]
        idx = {r["seq"]: i for i, r in enumerate(m)}
        fixed = []
        wait = 0
        for a, b in zip(m, m[1:], strict=False):
            if a["kind"] == "WAIT_BEGIN":
                need(b["kind"] == "WAIT_END", "incomplete WAIT at controller markers")
                wait += b["mono_us"] - a["mono_us"]
                fixed.append(0)
            else:
                fixed.append(max(0, b["mono_us"] - a["mono_us"] - 1))
        # first DEMAND .. wave/remap DONE lies within a measured callback. Empty
        # waves have no measured start. Keep pre/post work fixed in this sensitivity.
        interior = list(fixed)
        for group, bounds in metadata.items():
            if group[0] == call and "first" in bounds:
                first, last = idx[bounds["first"]], idx[bounds["done"]]
                for edge in range(first, last):
                    interior[edge] = 0
        jobs = []
        job_ids = []
        for context, key in zip(logical, admissions, strict=True):
            if context[0] != call or context not in retained:
                continue
            origin, expert, role = context[:4], context[4], context[5]
            consumer = (*origin[:3], origin[3] + 1) if role == "preload" else origin
            need(
                expert in demand_order[consumer] and role in ("demand", "preload"),
                "confirmed target consumer missing",
            )
            release, deadline = idx[metadata[origin]["first"]], idx[metadata[consumer]["done"]]
            left, right = service[key]
            need(t[release] <= left <= right <= t[deadline], "service outside relaxed job window")
            jobs.append((release, deadline, max(0, right - left - 1)))
            job_ids.append(context)
        elapsed = calls[call, "CALL_END"] - calls[call, "CALL_BEGIN"]
        if capture_windows is not None:
            capture_windows(
                call,
                t,
                fixed,
                interior,
                jobs,
                job_ids,
                wait + sum(r["kind"] == "WAIT_BEGIN" for r in m),
            )
        fixed_min = lower_bound(t, fixed, jobs)
        interior_min = lower_bound(t, interior, jobs)
        free_min = lower_bound(t, [0] * len(fixed), jobs)
        calls_report[str(call)] = {
            "historical_journal_us": elapsed,
            "retained_jobs": len(jobs),
            "wait_us": wait,
            "sum_retained_service_us_minus_resolution": sum(j[2] for j in jobs),
            "fixed_nonwait_saving_upper_us": min(
                elapsed + 1 - fixed_min, wait + sum(r["kind"] == "WAIT_BEGIN" for r in m)
            ),
            "observed_callback_interiors_free_saving_upper_us": elapsed + 1 - interior_min,
            "all_other_uninstrumented_work_free_saving_upper_us": elapsed + 1 - free_min,
        }
    n = sum(v["historical_journal_us"] for v in calls_report.values())
    return {
        "calls": calls_report,
        "historical_prefill_journal_us": n,
        "diagnostic_ten_percent_us": n / 10,
        "matched_jobs": sum(retained.values()),
        "removed_jobs": len(logical) - sum(retained.values()),
        "added_jobs_fully_credited_as_free": sum(target.values()) - sum(retained.values()),
        "fixed_nonwait_saving_upper_us": sum(
            v["fixed_nonwait_saving_upper_us"] for v in calls_report.values()
        ),
        "observed_callback_interiors_free_saving_upper_us": sum(
            v["observed_callback_interiors_free_saving_upper_us"] for v in calls_report.values()
        ),
        "all_other_uninstrumented_work_free_saving_upper_us": sum(
            v["all_other_uninstrumented_work_free_saving_upper_us"] for v in calls_report.values()
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, default=ROOT / "results" / C163)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir()
    try:
        report = {"freeze_sha256": sha(UNIT / "time_protocol.md"), "arms": {}}
        for arm in ("c163-on-1", "c163-on-2"):
            initial, final, rows, routing, _ = inputs(args.raw_dir, args.evidence_dir, arm)
            replay(initial, final, rows, routing)
            report["arms"][arm] = {}
            for mode in ("early", "late"):
                controls = [Fixture(initial, mode, protect) for protect in (False, True)]
                for fixture in controls:
                    fixture.run([r for r in routing if r["call_id"] in (9, 10)])
                report["arms"][arm][mode] = arm_report(rows, routing, *controls)
        temp = args.new_output_dir / ".receipt"
        with temp.open("x") as out:
            json.dump(report, out, indent=2)
            out.write("\n")
        os.replace(temp, args.new_output_dir / "receipt.json")
    except Exception as exc:
        (args.new_output_dir / "FAIL.txt").write_text(str(exc) + "\n")
        raise


if __name__ == "__main__":
    main()
