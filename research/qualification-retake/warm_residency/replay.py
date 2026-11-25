"""Replay a host victim LRU on the four validated C294 primary-cache journals."""

import argparse
import bisect
import hashlib
import io
import itertools
import json
import resource
import signal
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import cache_boundary as boundary  # noqa: E402

EXPERT = 13_219_200
STOP = 39 * 1024**3 // 2
UNIVERSE = 36 * 128
MEASURED = {
    "nvme_r0_gate/e20_measured/receipt.json": "54d66b2e7e8578fd85db4a7e19faa80cae98c658497b7b4096025c40768064c2",  # noqa: E501
    "nvme_conversation/evidence-20261124-r1/evidence.json": "f64067231b0936d82ce822ca782adfdb00bb9134b60d46fdc6a5bac3e6d64f74",  # noqa: E501
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def checked(path, expected):
    b = path.read_bytes()
    boundary.require(sha(b) == expected, "changed input")
    return b


class Bounds:
    """Intervals of recency for keys with unconstrained initial membership/order."""

    def __init__(self, capacity, n):
        self.cap = capacity
        self.n = n
        self.t = 0
        self.low = [0] * n
        self.high = [0] * n
        self.low_sorted = self.low.copy()
        self.high_sorted = self.high.copy()

    def advance(self, key, forced):
        self.t += 1
        # A positive lower timestamp proves the key was inserted or touched.
        # Other keys tied at zero (unknown prehistory) can never have a positive timestamp.
        possible = self.n - bisect.bisect_right(self.low_sorted, self.high[key]) < self.cap
        newer_possible = self.n - bisect.bisect_right(self.high_sorted, self.low[key])
        newer_possible -= self.high[key] > self.low[key]
        certain = self.low[key] > 0 and newer_possible < self.cap
        boundary.require(not certain or possible, "invalid recency interval")
        if forced or certain:
            i = bisect.bisect_left(self.low_sorted, self.low[key])
            self.low_sorted.pop(i)
            self.low_sorted.append(self.t)
            self.low[key] = self.t
        if forced or possible:
            i = bisect.bisect_left(self.high_sorted, self.high[key])
            self.high_sorted.pop(i)
            self.high_sorted.append(self.t)
            self.high[key] = self.t
        return certain, possible


class VictimCache:
    def __init__(self, capacity, content=()):
        self.capacity = capacity
        self.cache = OrderedDict.fromkeys(content)

    def advance(self, key, forced):
        hit = key in self.cache
        if forced or hit:
            self.cache[key] = None
            self.cache.move_to_end(key)
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
        return hit


def fixture():
    # Exhaust every 4-operation word of lookups/inserts, every ordered initial
    # cache of length <=2, with three distinct identities. Retain a genuine ambiguity.
    n, k = 3, 2
    starts = [c for size in range(k + 1) for c in itertools.permutations(range(n), size)]
    actions = list(itertools.product(range(n), (False, True)))
    words = ambiguous = 0
    for word in itertools.product(actions, repeat=4):
        concrete = [VictimCache(k, state) for state in starts]
        bounds = Bounds(k, n)
        for key, insert in word:
            lo, hi = bounds.advance(key, insert)
            cases = [c.advance(key, insert) for c in concrete]
            boundary.require(lo <= all(cases) and any(cases) <= hi, "unsound interval")
            ambiguous += any(cases) != all(cases)
        words += 1
    boundary.require(ambiguous > 0, "missing ambiguous fixture")
    return {
        "capacity": k,
        "identities": n,
        "ordered_initial_states": len(starts),
        "event_words": words,
        "ambiguous_prefixes": ambiguous,
    }


def primary(raw, name):
    _, proof = boundary.audit_arm(raw, name)
    directory = raw / (name + ".native")
    blobs = {
        f: checked(directory / f, proof["source_sha256"][f]) for f in ("initial.json", "events.tsv")
    }
    initial = json.loads(blobs["initial.json"])
    layers = sorted(initial["layers"], key=lambda r: r["layer"])
    tiers = [r["native_cache_buffer"] for r in layers]
    boundary.require(
        set(tiers) == {"CPU", "CUDA0"}
        and all(r["logical_bytes_per_load"] == EXPERT for r in layers),
        "invalid tier/bytes",
    )
    slots = [[(e, g) for e, g, _, _ in row] for row in boundary.slots(initial)]
    journal = io.StringIO(blobs["events.tsv"].decode())
    boundary.require(next(journal).strip() == boundary.HEADER, "event header")
    stream = []
    for line in journal:
        kind, _, call, _, layer, expert, slot, gen, *_ = map(int, line.split())
        if kind != 4:
            continue
        old, oldgen = slots[layer][slot]
        if gen == oldgen:
            continue
        slots[layer][slot] = (expert, gen)
        stream.append(
            (
                "prefill" if call == 0 else "decode",
                tiers[layer],
                128 * layer + expert,
                128 * layer + old if old >= 0 else None,
            )
        )
    for phase in ("prefill", "decode"):
        cnt = proof["counts"]
        subtotal = [row for row in stream if row[0] == phase]
        boundary.require(
            len(subtotal) == cnt[phase + "_new"] == cnt[phase + "_publications"],
            "fixed primary stream not conserved",
        )
        boundary.require(
            sum(row[3] is not None for row in subtotal) == cnt[phase + "_evictions"],
            "victims not conserved",
        )
    boundary.require(cnt["decode_new"] == cnt["decode_miss"], "unserved decode miss")
    return stream, proof["source_sha256"]


def summarise(rows, capacity):
    exact = VictimCache(capacity)
    bounds = Bounds(capacity, UNIVERSE)
    groups = {}
    for phase, tier, asked, old in rows:
        c = groups.setdefault((phase, tier), Counter())
        lo, hi = bounds.advance(asked, False)
        hit = exact.advance(asked, False)
        boundary.require(lo <= hit <= hi, "empty-state witness outside interval")
        c.update(lookups=1, cold_hits=int(hit), min_hits=int(lo), max_hits=int(hi))
        if old is not None:
            old_lo, old_hi = bounds.advance(old, True)
            copied = not exact.advance(old, True)
            c.update(
                evictions=1,
                cold_insert_copies=int(copied),
                min_insert_copies=int(not old_hi),
                max_insert_copies=int(not old_lo),
            )
    totals = {}
    for phase in ("prefill", "decode", "workload"):
        selected = [v for (p, _), v in groups.items() if phase == "workload" or p == phase]
        merged = sum(selected, Counter())
        for key in selected[0]:
            merged.setdefault(key, 0)
        totals[phase] = {
            **merged,
            "original_bytes": EXPERT * merged["lookups"],
            "cold_saved_bytes": EXPERT * merged["cold_hits"],
            "cold_insert_copy_bytes": EXPERT * merged["cold_insert_copies"],
            "min_hit_fraction": merged["min_hits"] / merged["lookups"],
            "max_hit_fraction": merged["max_hits"] / merged["lookups"],
        }
    return {"by_phase": totals, "by_tier": {f"{k[0]}_{k[1]}": dict(v) for k, v in groups.items()}}


def main(raw, out):
    out.mkdir()
    start = time.monotonic()
    result = {
        "status": "FAIL_PRESERVED",
        "forwards": 0,
        "protocol_sha256": sha((HERE / "protocol.md").read_bytes()),
        "script_sha256": sha(Path(__file__).read_bytes()),
    }
    try:
        signal.alarm(60)
        result["fixture"] = fixture()
        peaks = {
            k: json.loads(checked(HERE.parent / k, v))["maxima"]["cgroup_peak_bytes"]
            for k, v in MEASURED.items()
        }
        budget = STOP - max(peaks.values())
        capacities = {"3GiB": 3 * 1024**3 // EXPERT, "E20_payload_only": budget // EXPERT}
        result.update(
            source_sha256=MEASURED,
            peak_bytes=peaks,
            preventive_stop_bytes=STOP,
            E20_headroom_bytes=budget,
            expert_bytes=EXPERT,
            capacity_slots=capacities,
            arms={},
        )
        for name in boundary.NAMES:
            events, hashes = primary(raw, name)
            result["arms"][name] = {
                "sources_sha256": hashes,
                "scenarios": {k: summarise(events, v) for k, v in capacities.items()},
            }
        result["status"] = "TRACE_DERIVED_FIXED_PRIMARY"
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        result["error"] = type(exc).__name__
    finally:
        signal.alarm(0)
    result["wall_s"] = round(time.monotonic() - start, 3)
    result["maxrss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if result["maxrss_kib"] > 256 * 1024 or result["wall_s"] > 60:
        result["status"] = "FAIL_BUDGET"
    with (out / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"])
    return int(result["status"] != "TRACE_DERIVED_FIXED_PRIMARY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, boundary.deadline)
    raise SystemExit(main(args.raw_dir, args.new_output_dir))
