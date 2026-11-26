"""Optimistic offline payload floor for the original C294 routed decode."""

import argparse
import hashlib
import heapq
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from expert_service_window_gate import events  # noqa: E402

CAMPAIGN = "c294-feature-ready-service-window-20261006"
MANIFEST = ROOT / "results" / CAMPAIGN / "raw-manifest.json"
MANIFEST_SHA = "5a689ed0c3e7e328973a12de229c3a6ff4e151c14d568d49e517ff7dee98fd84"
EXPERT_BYTES = 13_219_200
LINK_BPS = 10_000_000_000
STEPS = 32
RATE = 6
MAX_LOADS = LINK_BPS * STEPS // (8 * EXPERT_BYTES * RATE)


def minimum(groups, capacity, initial=None, *, eligible_initial=None):
    """Optimal mandatory insertions for pinned groups and a given or free warm start."""
    end = len(groups) + 1
    first_use = {}
    next_uses = []
    for step in range(len(groups) - 1, -1, -1):
        cohort = groups[step]
        if len(cohort) > capacity or len(cohort) != len(set(cohort)):
            raise ValueError("incompatible pin set")
        next_uses.append([first_use.get(key, end) for key in cohort])
        for key in cohort:
            first_use[key] = step
    if initial is None:
        eligible = first_use if eligible_initial is None else first_use.keys() & eligible_initial
        initial = sorted(eligible, key=lambda key: (first_use[key], key))[:capacity]
    elif eligible_initial is not None:
        raise ValueError("choose a fixed or an eligible initial set")
    if len(initial) > capacity or len(set(initial)) != len(initial):
        raise ValueError("invalid initial cache")
    resident = {key: first_use.get(key, end) for key in initial}
    victims = [(-step, key) for key, step in resident.items()]
    heapq.heapify(victims)
    loads = 0
    for cohort, following in zip(groups, reversed(next_uses), strict=True):
        # Take every pin out of victim selection, including the current hits.
        loads += sum(resident.pop(key, None) is None for key in cohort)
        while len(resident) + len(cohort) > capacity:
            priority, key = heapq.heappop(victims)
            if resident.get(key) == -priority:
                del resident[key]
        for key, next_use in zip(cohort, following, strict=True):
            resident[key] = next_use
            heapq.heappush(victims, (-next_use, key))
    return loads


def first_capacity(loads, lower, upper):
    if loads(upper) > MAX_LOADS:
        raise ValueError("upper capacity does not meet payload budget")
    while lower < upper:
        middle = (lower + upper) // 2
        if loads(middle) <= MAX_LOADS:
            upper = middle
        else:
            lower = middle + 1
    return lower


def solve(groups, observed):
    by_layer = [groups[layer::36] for layer in range(36)]

    def uniform(slots):
        return sum(minimum(stream, slots) for stream in by_layer)

    def pooled(slots):
        return minimum(groups, slots)

    result = {}
    for name, fn, capacity, max_slots in (
        ("uniform_slots_per_layer", uniform, 40, 128),
        ("pooled_slots_total", pooled, 40 * 36, 128 * 36),
    ):
        floor = fn(capacity)
        edge = first_capacity(fn, 4, max_slots)
        if floor > observed:
            raise ValueError("ideal policy exceeds observed loads")
        result[name] = {
            "capacity": capacity,
            "min_loads": floor,
            "min_payload_bytes": floor * EXPERT_BYTES,
            "min_slots_for_six": edge,
            "loads_at_edge": fn(edge),
            "loads_one_below": fn(edge - 1) if edge > 4 else None,
        }
    return result


def read_arm(path, expected):
    if path.stat().st_size != expected["bytes"]:
        raise ValueError("C294 size mismatch")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("C294 digest mismatch")
    rows = events(path, True)
    routes = {}
    observed = 0
    read_sizes = set()
    for row in rows:
        call, layer = row["call"], row["layer"]
        if not call:
            continue
        if row["kind"] == 2:
            routes[call, layer] = []
        elif row["kind"] == 3:
            routes[call, layer].append(layer * 128 + row["expert"])
        elif row["kind"] == 6:
            read_sizes.add(row["bytes"])
        elif row["kind"] == 10:
            observed += 1
    expected_order = [(call, layer) for call in range(1, STEPS + 1) for layer in range(36)]
    if list(routes) != expected_order or any(len(v) != 4 for v in routes.values()):
        raise ValueError("C294 routed step ordering or top-k changed")
    if read_sizes != {EXPERT_BYTES // 3}:
        raise ValueError("expert component size changed")
    groups = [tuple(sorted(values)) for values in routes.values()]
    return groups, observed


def audit(raw):
    data = MANIFEST.read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA:
        raise ValueError("C294 manifest changed")
    manifest = {entry["path"]: entry for entry in json.loads(data)["files"]}
    arms = {}
    for case in ("nominal153", "code153"):
        for repeat in (2, 3):
            name = f"c294-{case}-{repeat}-on.native"
            rel = Path(name) / "events.tsv"
            expected = manifest[str(Path("results") / CAMPAIGN / "raw" / rel)]
            groups, observed = read_arm(raw / rel, expected)
            arms[name] = {
                "trace_sha256": expected["sha256"],
                "route_set_sequence_sha256": hashlib.sha256(
                    json.dumps(groups, separators=(",", ":")).encode()
                ).hexdigest(),
                "observed_loads": observed,
                "floor": solve(groups, observed),
            }
    return {
        "evidence": "FORMAL_CONDITIONAL",
        "steps": STEPS,
        "expert_bytes": EXPERT_BYTES,
        "link_gross_bps": LINK_BPS,
        "budget_loads_at_six_steps_s": MAX_LOADS,
        "arms": arms,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.new_output_dir.mkdir()
    try:
        result = audit(args.raw_dir)
    except FileNotFoundError:
        result = {"status": "NOT_RUN_RAW_REQUIRED"}
    except (ValueError, KeyError, OSError) as exc:
        result = {"status": "FAIL", "type": type(exc).__name__, "reason": str(exc)}
    pending = args.new_output_dir / ".pending"
    pending.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n")
    pending.replace(args.new_output_dir / "receipt.json")
    return int("arms" not in result)


if __name__ == "__main__":
    raise SystemExit(main())
