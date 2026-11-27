"""Price an optimistic direct destination and the minimum remaining READ reduction."""

import argparse
import json
from bisect import bisect_right
from functools import cache, partial
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LOOK = run_path(HERE / "lookahead.py")
Job, need, sha, limits = (LOOK[k] for k in ("Job", "need", "sha", "LIMITS"))
MILLION = 1_000_000
METHOD = "69ed35c5007b9e813ebac67f6f55fe6816929617dcb82d430243a686793d9392"
SIMULATOR = "dbaa716760a3c5592ffa298ec835a3d2d287dd95fe9b0341e42b93db9e4791f6"


def restore(witness):
    calls, seen = [], set()
    for opening, rows in witness:
        groups = [[] for _ in opening[1:]]
        events = {}
        for key, lane, begin, ready, put, end in rows:
            group = bisect_right(opening, put) - 1
            need(
                0 <= group < len(groups) and begin < ready == put < end and key not in seen,
                "lost original service or repeated generation",
            )
            seen.add(key)
            groups[group].append(Job(key, group, ready - begin, end - put))
            events[key] = (lane, begin, ready, put, end)
        LOOK["audit"](groups, 0, opening, events)
        calls.append(groups)
    need(len(calls) == 48 and len(seen) == 2354, "reference calls or generations")
    return calls


def clocks(calls, lead, free_sets, saving, exterior):
    result = exterior.copy()
    for num, groups in enumerate(calls, 1):
        repriced = [
            [
                Job(
                    j.order,
                    j.group,
                    (j.read * (MILLION - saving) + MILLION - 1) // MILLION,
                    0 if free_sets else j.put,
                )
                for j in jobs
            ]
            for jobs in groups
        ]
        floor = LOOK["floor"](repriced, lead)
        if num <= 46:
            result["first_final"] += floor
        if num >= 3:
            result["decode"] += floor
    return result


def threshold(price):
    def fits(row):
        return all(row[k] <= limit for k, limit in limits.items())

    initial = price(0)
    if fits(initial):
        return dict(min_read_reduction_ppm=0, current_floor_ns=initial, at_cut_ns=initial)
    if not fits(price(MILLION)):
        return dict(
            min_read_reduction_ppm=None, current_floor_ns=initial, free_read_floor_ns=price(MILLION)
        )
    lo, hi = 0, MILLION
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fits(price(mid)):
            hi = mid
        else:
            lo = mid
    need(not fits(price(lo)) and fits(price(hi)), "integer break-even")
    return dict(
        min_read_reduction_ppm=hi,
        current_floor_ns=initial,
        at_cut_ns=price(hi),
        one_ppm_less_ns=price(lo),
    )


def study(bound, directory):
    prior = directory / "lookahead.json"
    look = json.loads(prior.read_bytes())
    need(
        sha(HERE / "service-price.md") == METHOD
        and sha(HERE / "lookahead.py") == SIMULATOR
        and look["source_sha256"] == SIMULATOR
        and sha(bound) == LOOK["PARENT"] == look["parent_sha256"]
        and look["classification"] == "SIMULATED_ORACLE",
        "protocol, simulator and parent",
    )
    parent = json.loads(bound.read_bytes())
    traces = {}
    for label, arms in look["traces"].items():
        file = directory / f"{label}-0.json"
        need(sha(file) == arms["0"]["witness_sha256"], "original schedule seal")
        calls = restore(json.loads(file.read_bytes()))
        exterior = parent["traces"][label]["outside_ns"]
        traces[label] = {}
        for lead in (0, 1):

            price = cache(partial(clocks, calls, lead, exterior=exterior))

            control = {k: v["lower_full_client_ns"] for k, v in arms[str(lead)]["clocks"].items()}
            need(price(False, 0) == control, "layer bound reconstruction")
            row = {
                key: threshold(partial(price, free))
                for key, free in (("original_sets", False), ("free_sets", True))
            }
            fits = all(v <= limits[k] for k, v in row["free_sets"]["current_floor_ns"].items())
            row["direct_destination"] = (
                "NECESSARY_FLOOR_FITS" if fits else "NO_GO_COPY_ELISION_ALONE"
            )
            traces[label][str(lead)] = row
    need(set(traces) == {"P97", "P106"}, "both traces")
    return dict(
        classification="TRACE_DERIVED_CONDITIONAL",
        traces=traces,
        parent_sha256=sha(prior),
        protocol_sha256=METHOD,
        program_sha256=sha(Path(__file__)),
        model_loads=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("bound", "schedules", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        record = study(a.bound, a.schedules)
    except Exception as exc:
        record = dict(
            classification="NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            reason=str(exc),
        )
    with (a.new_output_dir / "service-price.json").open("x") as f:
        json.dump(record, f, indent=2, allow_nan=False, sort_keys=True)
        f.write("\n")
    print(record["classification"], record.get("reason", ""))
    raise SystemExit(record["classification"] != "TRACE_DERIVED_CONDITIONAL")
