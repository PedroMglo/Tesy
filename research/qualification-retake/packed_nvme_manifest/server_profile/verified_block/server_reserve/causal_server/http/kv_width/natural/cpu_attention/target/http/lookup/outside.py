"""Bound the nominal deadline using each native prefill clock and every eligible T1 key."""

import argparse
from collections import Counter
from fractions import Fraction
from math import ceil
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OFFER = run_path(str(HERE / "offers.py"))
BANK, HTTP, G, need, save = (OFFER[k] for k in ("B", "HTTP", "G", "need", "save"))
TRACE = BANK["B"]
METHOD = "26e0a2a73cf1c5b36ec45346c7500076dedc1dbd5d26301b706e521fb4380522"
PRIOR = "67981e087f60d99bb6991fca60b61721f70373749262b39e49902c3c2d9d3b90"
CUT = 44


def partition(begin, end, spans):
    """Partition one serialized sequence of remap callbacks on the host clock."""
    if not spans or end < begin:
        raise ValueError("incomplete call")
    gaps = Counter()
    counts = Counter()
    tier_gaps = Counter()
    previous = None
    cursor = begin
    inside = 0
    for start, stop, site in spans:
        if not cursor <= start <= stop <= end:
            raise ValueError("callback crosses its call or another callback")
        if previous is None:
            category = "entry"
        elif previous[1] != site[1]:
            category = "between_tiles"
        elif previous[2] != site[2]:
            category = "between_layers"
        else:
            category = "within_layer"
        elapsed = start - cursor
        gaps[category] += elapsed
        counts[category] += 1
        if previous is not None:
            left = "CPU" if previous[2] < 25 else "CUDA0"
            right = "CPU" if site[2] < 25 else "CUDA0"
            tier_gaps[(category, left, right)] += elapsed
        inside += stop - start
        cursor, previous = stop, site
    gaps["return"] += end - cursor
    counts["return"] += 1
    outside = sum(gaps.values())
    need(
        inside + outside == end - begin and sum(counts.values()) == len(spans) + 1,
        "wall-clock conservation",
    )
    return dict(
        span_ns=end - begin,
        callbacks=len(spans),
        remap_union_ns=inside,
        outside_ns=outside,
        gap_ns=dict(gaps),
        gap_counts=dict(counts),
        gap_by_transition_ns={" / ".join(k): v for k, v in sorted(tier_gaps.items())},
    )


def fixture():
    one = (2, 1, 0, 0)
    two = (2, 1, 0, 1)
    p = partition(2, 11, [(3, 6, one), (6, 8, two)])
    need(
        p["outside_ns"] == 4
        and p["gap_counts"]["within_layer"] == 1
        and p["gap_ns"]["within_layer"] == 0,
        "touching calls",
    )
    for spans in ([], [(1, 4, one)], [(10, 12, one)], [(3, 6, one), (5, 8, two)]):
        try:
            partition(2, 11, spans)
        except ValueError:
            continue
        raise ValueError("invalid intervals accepted")


def native_arm(a, name, tiers, keys, data, steps, reference):
    rows, tiers, ids = TRACE["trace_arm"](a, name, tiers, data, steps)
    need(
        TRACE["account"](rows, tiers) == reference["population"]
        and ids == reference["target_id_digests"],
        "exact population and both sets of target IDs",
    )
    host = TRACE["C"]["NATIVE"]["host_trace"](rows)
    waves, jobs = TRACE["C"]["timeline"](rows)
    need(
        [(w.site[0], w.start, w.end) for w in waves] == host["callback_spans"],
        "same serialized callbacks in two readers",
    )
    calls = []
    for call, geom in zip(host["calls"][:2], ([5], [32, 32, 32, 32, 20]), strict=True):
        number = call["number"]
        need([g[0] for g in call["geometry"]] == geom, "original geometry")
        spans = [(w.start, w.end, w.site) for w in waves if w.site[0] == number]
        calls.append(
            dict(call=number, tiles=geom, **partition(call["enter_ns"], call["return_ns"], spans))
        )
    early = Counter()
    full = Counter()
    for (layer, _, _, expert), site in jobs.items():
        call = site[0]
        k = (layer, expert)
        if call >= 3 and k in keys:
            full[k] += 1
            if call < 3 + CUT:
                early[k] += 1
    return dict(calls=calls, outside_ns=sum(c["outside_ns"] for c in calls)), tiers, (early, full)


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit and OFFER["J"]["AUDIT"]["sha"](HERE / "outside-protocol.md") == METHOD,
        "sealed method",
    )
    fixture()
    offers = G["read"](HERE / "offers-result.json", PRIOR)
    env = G["read"](HERE / "envelope-result.json", BANK["ENVELOPE"])
    physical = G["read"](HERE / "http-result.json", env["four_arm_review_sha256"])
    HTTP["R"]["reopen"](a.family, physical["family_sha256"])
    graph, marks = OFFER["J"]["graphs"](a.family, a.lookup_run, CUT)
    turn = env["turns"]["T2"]
    need(
        turn["first_final_sample"] == CUT + 1 and len(marks) == turn["confirmed"] == 47,
        "client cut",
    )
    ref = G["read"](HERE.parent / "reload-result.json", OFFER["ENV"]["RELOADS"])
    data, steps = HTTP["R"]["cases"](a)
    seq, _, _ = OFFER["offered"](a)
    keys = set(seq)
    limit = offers["capacity"]
    need(len(keys) == offers["distinct_offers"] and limit == OFFER["CAP"], "eligible payloads")
    arms = {}
    tiers = prior = None
    for label in ("P106", "P97"):
        arms[label], tiers, counts = native_arm(a, label, tiers, keys, data, steps, ref)
        if prior is not None:
            need(counts == prior, "same early and full counts by exact identity")
        prior = counts
    early, full = counts
    most = sum(v for _, v in early.most_common(limit))
    need(
        most
        <= sum(v for _, v in full.most_common(limit))
        == offers["separate_top353"]["all_decode"],
        "reopened finite-capacity bound",
    )
    credit = Fraction(most * BANK["WINDOW"], BANK["RATE"])
    prices = {}
    for name, result in turn["scenarios"].items():
        first = min(result["witnesses"], key=lambda v: v["producer_until_first_final_us"])
        paths = OFFER["ENV"]["frontier"](graph[name], 46, CUT)
        need(
            min(OFFER["ENV"]["clocks"](p)[0] for p in paths)
            == first["producer_until_first_final_us"],
            "reopened earliest compatible path",
        )
        # Round the client's floating-point budget upwards to the next microsecond.
        initial = Fraction(ceil(Fraction(str(first["available_prefill_s_for_ten"])) * 10**6), 10**6)
        allowed = initial + credit
        prices[name] = dict(
            allowed_prefill_before_credit_s=float(initial),
            maximum_allowed_prefill_s=float(allowed),
            lower_first_final_s={
                label: float(10 + Fraction(arm["outside_ns"], 10**9) - allowed)
                for label, arm in arms.items()
            },
        )
    named = {}
    for profile, result in offers["scenarios"]["future_volume"]["profiles"].items():
        floor = result["min_prefill_service_s"]
        first = result["at_full_exposure"]["first_final_s"]
        named[profile] = dict(
            maximum_allowed_prefill_s=10 - first + floor,
            lower_first_final_s={
                label: first + max(0, arm["outside_ns"] / 10**9 - floor)
                for label, arm in arms.items()
            },
        )
    favourable = prices["all_observed_serial"]["lower_first_final_s"].values()
    return dict(
        status="TRACE_DERIVED_OUTSIDE_REMAP",
        decision="NO_GO_FIXED_OUTSIDE" if min(favourable) > 10 else "INCONCLUSIVE",
        commit=commit,
        tree=tree,
        protocol_sha256=METHOD,
        offers_sha256=PRIOR,
        new_requests=0,
        new_model_starts=0,
        journals=arms,
        eligible_keys=len(keys),
        bank_capacity=limit,
        reservations_early_top=most,
        reservations_all_decode_top=offers["separate_top353"]["all_decode"],
        aligned_bytes_per_reservation=BANK["WINDOW"],
        assumed_rate_Bps=BANK["RATE"],
        maximum_early_credit_s=float(credit),
        per_graph=prices,
        named_future_witness=named,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "family", "lookup-run", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", study(a))
