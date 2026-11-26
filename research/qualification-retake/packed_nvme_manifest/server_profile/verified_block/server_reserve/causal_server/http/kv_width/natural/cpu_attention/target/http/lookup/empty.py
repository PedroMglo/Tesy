"""Reconcile which prefill gaps follow an entirely empty routed wave."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OUT = run_path(str(HERE / "outside.py"))
TRACE, HTTP, G, need, save = (OUT[k] for k in ("TRACE", "HTTP", "G", "need", "save"))
METHOD = "5c8784c29fe3c71f70a37552d8b4ba2ddea478b23034992621e78564995289cb"
PRIOR = "168a3bf6ad5fcda1550c835334a902cd410bf544245fbbbb23718226e1f91052"


def rank_counts(waves, counts):
    """Credit each logical routed occurrence to its unique consuming wave."""
    remaining = set(counts)
    sizes = []
    empty_seen = False
    for experts in waves:
        if not experts <= remaining or (experts and empty_seen):
            raise ValueError("repeated expert or active wave after empty suffix")
        sizes.append(sum(counts[k] for k in experts))
        remaining.difference_update(experts)
        empty_seen |= not experts
    if remaining or sum(sizes) != sum(counts.values()):
        raise ValueError("unserved rank")
    return sizes


def following(spans, end):
    for i, (start, stop) in enumerate(spans):
        after = spans[i + 1][0] if i + 1 < len(spans) else end
        if not start <= stop <= after:
            raise ValueError("overlapping callbacks")
        yield after - stop


def fixture():
    route = Counter((4, 6, 4, 9))
    need(rank_counts([{4, 6, 9}, set()], route) == [4, 0], "repeated ranks")
    need(list(following([(2, 7), (8, 9)], 14)) == [1, 5], "last wave to return")
    for waves in ([{4}, {4, 6, 9}], [{4}, set(), {6, 9}], [{4, 6}]):
        try:
            rank_counts(waves, route)
        except ValueError:
            continue
        raise ValueError("invalid routing accepted")


def arm(a, name, tiers, outside, reference, data, steps):
    rows, tiers, ids = TRACE["trace_arm"](a, name, tiers, data, steps)
    need(
        TRACE["account"](rows, tiers) == reference["population"]
        and ids == reference["target_id_digests"],
        "same target and generations",
    )
    host = TRACE["C"]["NATIVE"]["host_trace"](rows)
    waves, jobs = TRACE["C"]["timeline"](rows)
    ranks = defaultdict(Counter)
    groups = defaultdict(list)
    for e in rows:
        if e.call in (1, 2) and e.kind == 27:
            ranks[e.call, e.tile, e.layer].update(e.a.to_bytes(4, "little"))
    for w in waves:
        if w.site[0] <= 2:
            groups[w.site[:3]].append(w)
    sizes = {}
    for site, ws in groups.items():
        logical = [{k[3] for k in w.demands} for w in ws]
        for w, count in zip(ws, rank_counts(logical, ranks[site]), strict=True):
            need(count or not w.reserved, "empty wave with a service reservation")
            sizes[w.site] = count
    need(ranks.keys() <= groups.keys(), "missing graph group")
    per_call = []
    signature = []
    for c, frozen in zip(host["calls"][:2], outside["calls"], strict=True):
        call = c["number"]
        ws = [w for w in waves if w.site[0] == call]
        need(call == frozen["call"] and len(ws) == frozen["callbacks"], "call scope")
        after = list(following([(w.start, w.end) for w in ws], c["return_ns"]))
        entry = ws[0].start - c["enter_ns"]
        grouped = defaultdict(Counter)
        for w, duration in zip(ws, after, strict=True):
            n = sizes[w.site]
            key = tiers[w.site[2]] + ("_active" if n else "_empty")
            row = grouped[key]
            row["waves"] += 1
            row["ranks"] += n
            row["reservations"] += len(w.reserved)
            row["gap_ns"] += duration
            signature.append((w.site, n, len(w.reserved)))
        need(
            entry + sum(after) == frozen["outside_ns"]
            and entry == frozen["gap_ns"]["entry"]
            and sum(v["ranks"] for v in grouped.values())
            == sum(sum(n.values()) for k, n in ranks.items() if k[0] == call)
            and sum(v["reservations"] for v in grouped.values())
            == sum(s[0] == call for s in jobs.values()),
            "gaps, target ranks and reservations",
        )
        per_call.append(dict(call=call, entry_ns=entry, classes=dict(grouped)))
    return per_call, signature, tiers


def compare(first, seconds):
    deficit = max(0.0, first - 10)
    return dict(
        prior_deficit_s=deficit,
        exposed_fraction_needed=(deficit / seconds if seconds > 0 and deficit <= seconds else None),
        new_first_final_floor_s=first - seconds,
        missing_s=max(0.0, deficit - seconds),
    )


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit
        and OUT["OFFER"]["J"]["AUDIT"]["sha"](HERE / "empty-protocol.md") == METHOD,
        "sealed method",
    )
    fixture()
    outside = G["read"](HERE / "outside-result.json", PRIOR)
    ref = G["read"](HERE.parent / "reload-result.json", OUT["OFFER"]["ENV"]["RELOADS"])
    data, steps = HTTP["R"]["cases"](a)
    journals = {}
    tiers = prior = None
    for name in ("P106", "P97"):
        calls, sig, tiers = arm(a, name, tiers, outside["journals"][name], ref, data, steps)
        if prior is not None:
            need(sig == prior, "identical wave, rank and generation counts in the two processes")
        prior = sig
        empty = {
            tier: sum(c["classes"].get(tier + "_empty", {}).get("gap_ns", 0) for c in calls)
            for tier in ("CPU", "CUDA0")
        }
        comparisons = {}
        for profile, ns in (("CPU", empty["CPU"]), ("both", sum(empty.values()))):
            scenarios = dict(
                outside["per_graph"], named_future=outside["named_future_witness"]["no_rescue"]
            )
            comparisons[profile] = {
                key: compare(v["lower_first_final_s"][name], ns / 10**9)
                for key, v in scenarios.items()
            }
        journals[name] = dict(calls=calls, gap_after_empty_ns=empty, scenarios=comparisons)
    decision = {}
    for variant in ("CPU", "both"):
        passthrough = [
            v["scenarios"][variant]["all_observed_serial"]["missing_s"] == 0
            for v in journals.values()
        ]
        decision[variant] = (
            "HEADROOM_ONLY"
            if all(passthrough)
            else ("INCONCLUSIVE" if any(passthrough) else "NO_GO_FIXED_GAPS")
        )
    return dict(
        status="TRACE_DERIVED_EMPTY_WAVE_GAPS",
        decision=decision,
        commit=commit,
        tree=tree,
        protocol_sha256=METHOD,
        outside_sha256=PRIOR,
        journals=journals,
        new_requests=0,
        new_model_starts=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", study(a))
