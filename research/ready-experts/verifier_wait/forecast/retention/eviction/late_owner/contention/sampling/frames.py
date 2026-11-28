"""Replay CPU promotions as physical-frame ownership changes against a copying reference."""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
X = run_path(HERE.parent / "mixed.py")
V, F, need, sha, save = (X[k] for k in ("V", "F", "need", "sha", "save"))
T = V["T"]
METHOD = "37362772533ec26b8777a55804e6a284c2a561f10a60d79dfbc5bb3b407962dc"
PARENT = "756cc9637c12c8b1d0d4ced3d12260eff21d553ce999bee891d4a405e5ff4566"
PAYLOAD = T["PAYLOAD"]
STRIDE = F["WINDOW"]


def rebind(primary, secondary, slot, source, target):
    """Transfer ownership with a permutation, preserving every physical frame index."""
    if source is None:
        if target is not None:
            primary[slot], secondary[target] = secondary[target], primary[slot]
        return
    primary[slot], secondary[source] = secondary[source], primary[slot]
    if target is not None and target != source:
        secondary[source], secondary[target] = secondary[target], secondary[source]


def matrices(key):
    return tuple(3 * key + i for i in range(3))


def verify(payload, primary, secondary, expected, cached):
    need(
        set(primary + secondary) == set(range(len(payload)))
        and len(payload) == len(primary) + len(secondary),
        "duplicated or lost physical frame",
    )
    need(
        all(payload[f] == matrices(key) for f, key in zip(primary, expected, strict=True))
        and all(
            key is None or payload[f] == matrices(key)
            for f, key in zip(secondary, cached, strict=True)
        ),
        "stale, missing or cross-component delivery",
    )


def evaluate():
    need(
        sha(HERE / "frames-protocol.md") == METHOD
        and sha(HERE / "evidence-tiers-20261128-r01/tiers.json") == PARENT,
        "registered parents",
    )
    tx, fx = V["sources"]()
    root = V["TIER"] / "evidence-tier-20261128-r01"
    witness = F["unpack"](root / "transactions.json.gz")
    freq = Counter({(layer, e): n for layer, e, n in witness["counts"]})
    seed = list(map(tuple, witness["seed"]))
    alt, info = T["run_order"](tx, witness["initial"], seed, freq, [252, 101], True)
    need(
        alt == fx and T["quotas"](freq) == [252, 101],
        "same sources and logical slots in both orders",
    )
    seq = [i for i, t in enumerate(tx) if t[2] < 25]

    def pipeline(i):
        call, tile, layer, *_ = tx[i]
        if call != 2:
            return call, 0
        return call, (max(0, 2 * tile - 3) if layer < 25 else min(9, 2 * tile))

    need(
        seq == [i for i in sorted(range(len(tx)), key=pipeline) if tx[i][2] < 25],
        "CPU order changed",
    )
    primary = list(range(1000))
    secondary = list(range(1000, 1252))
    expected = [None] * 1000
    generations = [None] * 1000
    for layer, s, e, g in witness["initial"]:
        if layer < 25:
            slot = layer * 40 + s
            need(expected[slot] is None, "initial slot")
            expected[slot], generations[slot] = 128 * layer + e, g
    need(None not in expected and len(set(expected)) == 1000, "initial CPU pool")
    present = set(expected)
    keys = [128 * layer + e for layer, e in seed if layer < 25 and 128 * layer + e not in present][
        -252:
    ]
    need(len(keys) == info["initial"][0] == 227, "causal host seed")
    cached = keys + [None] * (252 - len(keys))
    payload = [matrices(k) if k is not None else None for k in expected + cached]
    writers = [None] * 1252
    rows = []
    phases = defaultdict(Counter)
    entry = None

    def state():
        return V["C"]["IV"]["digest"]([primary, secondary, expected, cached, generations])

    verify(payload, primary, secondary, expected, cached)
    extent = len(keys)
    for i in seq:
        call, tile, layer, s, gen, e, victim = tx[i]
        tier, src, dst = fx[i]
        if call >= 3 and entry is None:
            entry = state()
        slot = 40 * layer + s
        key, old = 128 * layer + e, 128 * layer + victim
        need(
            tier == 0 and generations[slot] + 1 == gen and expected[slot] == old,
            "primary generation",
        )
        victim_frame = primary[slot]
        hit_frame = secondary[src] if src is not None else None
        victim_writer = writers[victim_frame] if dst is not None else None
        phase = "prefill" if call <= 2 else "early_decode" if call <= 46 else "tail"
        a = phases[phase]
        a.update(jobs=1, hits=int(src is not None), captures=int(dst is not None))
        if src is not None:
            need(cached[src] == key, "wrong retained expert")
            cached[src] = None
        if dst is not None:
            cached[dst] = old
        expected[slot], generations[slot] = key, gen
        rebind(primary, secondary, slot, src, dst)
        f = primary[slot]
        source_writer = writers[f]
        if src is None:
            payload[f] = matrices(key)
            writers[f] = i
        else:
            need(f == hit_frame and payload[f] == matrices(key), "copied or wrong hit")
        if dst is not None:
            need(
                secondary[dst] == victim_frame and payload[victim_frame] == matrices(old),
                "copied victim",
            )
        verify(payload, primary, secondary, expected, cached)
        extent = max(extent, sum(k is not None for k in cached))
        rows.append((i, f, src is not None, source_writer, victim_frame, victim_writer))
    total = sum(phases.values(), Counter())
    need(
        total["jobs"] == 1594 and total["hits"] == 469 and extent == 252 and entry,
        "coverage or occupancy",
    )
    service = X["ORIGINAL"] / "service.json.gz"
    need(sha(service) == V["SERVICE"], "native clock input")
    timing = {}
    for tag, observed in F["unpack"](service).items():
        native = observed["jobs"]
        checks = Counter()
        conflict = []
        minimum = {}
        for i, f, hit, source_writer, victim_frame, victim_writer in rows:
            j = native[i]
            call, tile, layer, s, gen, e, _ = tx[i]
            need(j[0] == [layer, s, gen, e] and j[1][:3] == [call, tile, layer], "journal binding")
            for name, prior, current, frame in (
                (
                    "promotion_at_reserve" if hit else "overwrite_at_first_set",
                    source_writer,
                    j[2] if hit else j[7],
                    f,
                ),
                ("capture_at_reserve", victim_writer, j[2], victim_frame),
            ):
                if prior is None:
                    continue
                need(prior < i, "forward source dependency")
                slack = current - native[prior][-1]
                checks[name] += 1
                minimum[name] = min(slack, minimum.get(name, slack))
                if slack < 0:
                    conflict.append([name, i + 1, prior + 1, frame, slack])
        timing[tag] = dict(comparisons=checks, minimum_slack_ns=minimum, conflicts=conflict)
    return dict(
        status="GO_CPU_OPERATOR_FIXTURE",
        evidence="FORMAL_DRAINED_OWNERSHIP_TRACE_DERIVED_DEPENDENCIES",
        method=METHOD,
        parent=PARENT,
        phases=phases,
        totals=total,
        active_frames=len(payload),
        primary_frames=len(primary),
        secondary_frames=len(secondary),
        secondary_peak=extent,
        arena_B=len(payload) * STRIDE,
        payload_capacity_B=len(payload) * PAYLOAD,
        padding_B=len(payload) * (STRIDE - PAYLOAD),
        avoided_hit_set_payload_B=total["hits"] * PAYLOAD,
        avoided_capture_payload_B=total["captures"] * PAYLOAD,
        paid_miss_payload_B=(total["jobs"] - total["hits"]) * PAYLOAD,
        entry_decode_state=entry,
        final_state=state(),
        ordered_actions_sha256=V["C"]["IV"]["digest"](rows),
        journals=timing,
        model_forwards=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        r = evaluate()
        if a.check:
            need(r == json.loads(a.check.read_bytes()), "published ownership and producer clocks")
        else:
            save(a.new_output_dir / "frames.json", r)
        print(r["status"], r["totals"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
