"""Bound two live prefill tiles, exact transport and a causal layout on the same client clock."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "layout.py")
SRC, need, LIMIT = (L[k] for k in ("SRC", "need", "LIMIT"))
union = L["B"]["reach"]["union_ns"]
PLAN = "46e0f9a215c173a5674c48c6e8947a12b85722864711e2fc3a3c0a9e5773b27a"
SCORING = "171e1bc51f55c7fe371e758eb0adbee77efb5a8ad76b95e1d29de600c108555d"
PAYLOAD, NS = 13_219_200, 10**9
SPEEDS = (8_000_000_000, 4_500_000_000)


def ceil_div(a, b):
    return -(-a // b)


def kept(lo, hi, free):
    need(lo <= hi, "reversed stage")
    return hi - lo - union((max(lo, a), min(hi, b)) for a, b in free if max(lo, a) < min(hi, b))


def pipeline(stages):
    """Earliest finish with two ordered stations and at most two tiles in flight."""
    front = tail = 0
    plan = []
    for a, b in stages:
        need(min(a, b) >= 0, "negative stage price")
        begin = max(front, plan[-2][3] if len(plan) >= 2 else 0)
        front = begin + a
        join = max(front, tail)
        tail = join + b
        plan.append([begin, front, join, tail])
    return plan


def markers(rows):
    calls, tiles, layers = {}, defaultdict(dict), defaultdict(list)
    for r in rows:
        if r.call not in (1, 2):
            continue
        if r.kind in (1, 2):
            calls[r.call, r.kind] = r.ns
        if r.call == 2 and r.kind in (3, 4):
            tiles[r.tile][r.kind] = r.ns
        if r.call == 2 and r.kind in (9, 23):
            layers[r.tile, r.layer, r.kind].append(r.ns)
    matrix = []
    for t in range(1, 6):
        last = 35 if t == 5 else 34
        need(
            all(
                bool(layers.get((t, layer, k))) == (layer <= last)
                for layer in range(36)
                for k in (9, 23)
            ),
            "target output selection",
        )
        span = [
            tiles[t][3],
            layers[t, 0, 9][0],
            layers[t, 24, 23][-1],
            layers[t, 25, 9][0],
            layers[t, last, 23][-1],
            tiles[t][4],
        ]
        need(span == sorted(span) and (not matrix or matrix[-1][-1] <= span[0]), "tile order")
        matrix.append(span)
    need(
        calls[1, 1] < calls[1, 2] <= calls[2, 1] <= matrix[0][0] and matrix[-1][-1] <= calls[2, 2],
        "external barrier",
    )
    return dict(calls=[[calls[c, 1], calls[c, 2]] for c in (1, 2)], tiles=matrix)


def credit(regions, order):
    ranks = [dict(zip(path, range(len(path)), strict=True)) for path in order]
    intervals, jobs = defaultdict(list), Counter()
    for call, _, layer, ids, lo, hi, _ in regions:
        jobs[call] += len(ids)
        chosen = {ranks[layer][e] for e in ids} if order else set()
        if any(i + 1 in chosen for i in chosen):
            intervals[call].append((lo, hi))
    return intervals, jobs


def budget(body, available):
    return dict(
        available_ns=available,
        minimum_payload_Bps=ceil_div(body * NS, available) if available > 0 else None,
        bytes_to_remove_at_wire=max(0, body - max(0, available) * SPEEDS[0] // NS),
        shortfall_at_wire_ns=max(0, ceil_div(body * NS, SPEEDS[0]) - available),
    )


def price(raw, marks, order):
    free, jobs = credit(raw["regions"], order)
    early = sum(union(free[c]) for c in range(3, 47))
    dec_credit = early + union(free[47]) + union(free[48])
    first, dec = (raw["before_ns"][k] for k in ("first_final", "decode"))
    pre = sum(b - a for a, b in marks["calls"])
    base = first - pre - early
    new_dec = dec - dec_credit
    dec_gap = max(0, new_dec - LIMIT["decode"])
    body = (jobs[1] + jobs[2]) * PAYLOAD
    need(jobs[1] + jobs[2] == 1263 and sum(jobs.values()) == 2354 and base >= 0, "phase cohorts")
    steps = [(kept(a, b, free[2]), kept(c, d, free[2])) for _, a, b, c, d, _ in marks["tiles"]]
    plan = pipeline(steps)
    bounds = [kept(*marks["calls"][0], free[1]), plan[-1][-1]]
    need(
        bounds[0] + bounds[1] <= pre - union(free[1]) - union(free[2]), "double credit or lost time"
    )
    at_speed = {}
    for speed in SPEEDS:
        floors = [max(v, ceil_div(jobs[i] * PAYLOAD * NS, speed)) for i, v in enumerate(bounds, 1)]
        first_floor = base + sum(floors)
        at_speed[str(speed)] = dict(
            charge_ns=floors,
            first_final_ns=first_floor,
            decode_ns=new_dec,
            still_needed_first_ns=max(0, first_floor - LIMIT["first_final"]),
            still_needed_decode_ns=dec_gap,
            decision="NO_GO_ISOLATED"
            if dec_gap or first_floor > LIMIT["first_final"]
            else "HEADROOM_ONLY",
        )
    return dict(
        payload_bytes=body,
        jobs_by_call=[jobs[1], jobs[2]],
        decode_early_credit_ns=early,
        decode_total_credit_ns=dec_credit,
        first_excluding_prefill_ns=base,
        prefill_control_ns=pre,
        stage_floor_ns=bounds,
        earliest_stage_plan_ns=plan,
        first_final_unlimited_Bps_ns=base + sum(bounds),
        limits_by_Bps=at_speed,
        perfect_prefill=budget(body, LIMIT["first_final"] - base),
        perfect_prefill_if_decode_just_meets_six=budget(
            body, LIMIT["first_final"] - base + dec_gap
        ),
    )


def link():
    ref = HERE.parents[3] / "qualification-retake/mxfp4_cross_role/causal_pool/link_floor/link.json"
    old = SRC["pinned"](ref, "5e134a1d7edbf4e5257d9dc6dc8d57b127be9244128866e823ed6a1f0a54f992")
    nvme = Path("/sys/class/nvme/nvme0")
    endpoint = (nvme / "device").resolve(strict=True)
    need((nvme / "model").read_text().strip() == old["nvme"], "NVMe identity")
    verified = {}
    for role, device in (("controller", endpoint), ("upstream_bridge", endpoint.parent)):
        observed = {"bdf": device.name} | {
            k: (device / k).read_text().strip() for k in old["devices"][role] if k != "bdf"
        }
        need(
            observed == old["devices"][role]
            and observed["max_link_speed"] == "16.0 GT/s PCIe"
            and int(observed["max_link_width"]) == 4,
            "link upper bound",
        )
        verified[role] = observed
    return dict(devices=verified, model=old["nvme"], raw_bytes_per_second=SPEEDS[0])


def run(archive, source, trained):
    layout = SRC["pinned"](trained, PLAN)
    result = SRC["pinned"](source / "receipt.json", SCORING)
    need(SRC["digest"](source / "regions.json.gz") == result["regions_sha256"], "regions")
    compact = json.loads(gzip.decompress((source / "regions.json.gz").read_bytes()))
    arms = {}
    for tag, previous in result["arms"].items():
        name, sha, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P97":
            path = root / "ON/raw/events.pfj"
            need(SRC["digest"](path) == previous["journal_sha256"], "P97")
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        else:
            need(
                SRC["digest"](root / "ON/observer/events.pfj") == previous["journal_sha256"], "P106"
            )
            _, rows, _, _ = SRC["Q"]["read_new"](root, sha)
        mark = markers(rows)
        before = dict(before_ns=previous["before_ns"], regions=compact[tag])
        arm = {"markers": mark}
        for role, path in (
            ("pipeline", []),
            ("numeric", [list(range(128))] * 36),
            ("trained", layout["order"]),
        ):
            arm[role] = price(before, mark, path)
            if role != "pipeline":
                dec = previous[role]["scopes"]["decode"]
                need(
                    arm[role]["decode_total_credit_ns"] == dec["covered_ns"],
                    "decode credit changed",
                )
        arms[tag] = arm
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        protocol_sha256=SRC["digest"](HERE / "pipeline-protocol.md"),
        program_sha256=SRC["digest"](HERE / "pipeline.py"),
        plan_sha256=PLAN,
        layout_receipt_sha256=SCORING,
        link=link(),
        arms=arms,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("archive", "layout-evidence", "trained-plan", "new-output-dir"):
        p.add_argument("--" + n, type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = run(a.archive, a.layout_evidence, a.trained_plan)
        pending = out / ".pending"
        pending.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        pending.rename(out / "receipt.json")
    except (OSError, ValueError, KeyError, AssertionError, TypeError) as exc:
        (out / "failure.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": repr(exc)}) + "\n"
        )
        raise
    print(SRC["digest"](out / "receipt.json"))
