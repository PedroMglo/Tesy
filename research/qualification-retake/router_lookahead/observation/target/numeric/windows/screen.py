"""Price observed C292 E33 decisions, whole reads and a shared FIFO at actual worker deadlines."""

import argparse
import hashlib
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from itertools import accumulate
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
DEMAND = HERE.parents[3] / "demand"
W = run_path(str(DEMAND / "deadlines/score.py"))
JOIN = run_path(str(HERE.parent / "join.py"))
M = W["M"]
need = JOIN["need"]
READ_WINDOW = W["WINDOW"]
RATE = 4_500_000_000
FAMILY = "e762554f1ab0372a9534da0ec857aaccf3fc82ddf4f586f2e84dca1df3a65156"
REVIEW = "fa9490aca066e4df0d44d7f457bc6732b6b6ef530aae6b80de4470ebdfda4e49"
JOURNAL = "cc2b79a1897f58da66018da9a2d11f204988bb0e2d456994061059ce992b5028"
RULES = "51a959b3c5a5994818fe91c50284e4fb61dd1bdf92127b3962c76a1872aa8212"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p, expected):
    need(sha(p) == expected, "unsealed file: " + p.name)
    return json.loads(p.read_bytes())


def available_clock(spans):
    """Measure time minus the union of native READs; a pause applies to both interval endpoints."""
    union = []
    for a, b in sorted(spans):
        need(0 <= a < b, "inverted read")
        if union and a <= union[-1][1]:
            union[-1] = (union[-1][0], max(b, union[-1][1]))
        else:
            union.append((a, b))
    lengths = [b - a for a, b in union]
    prefix = [0, *accumulate(lengths)]
    ends = [b for _, b in union]

    def time(t):
        i = bisect_right(ends, t)
        partial = max(0, t - union[i][0]) if i < len(union) else 0
        return t - prefix[i] - partial

    return time, sum(lengths)


def retime(sites, clock):
    return [
        (i, clock(r), group, offers, {e: tuple(map(clock, ds)) for e, ds in matched.items()})
        for i, r, group, offers, matched in sites
    ]


def group_of(call, layer):
    return ("prefill" if call == 1 else "decode") + ("/CPU" if layer < 25 else "/CUDA")


def gather(rows, join):
    deadlines = W["job_deadlines"](rows)
    predictions, reserve, eligible, look, actual = (defaultdict(dict) for _ in range(5))
    ends, original = {}, []
    total_reads = Counter()
    calls = {}
    elapsed = Counter()
    for i, r in enumerate(rows):
        site = r.call, r.tile, r.layer
        k = M["AUDIT"]["identity"](r)
        if r.kind == 33:
            need(r.c not in predictions[site], "duplicate position in prediction")
            predictions[site][r.c] = JOIN["quartet"](r.a)
            ends[site] = i, r.ns
        elif r.kind == 27:
            actual[site][r.b] = JOIN["quartet"](r.a)
        elif r.kind == 11:
            reserve[site][k] = i, r.wave
        elif r.kind == 34:
            wave = (*site, r.wave)
            look[wave][r.expert] = r.a
        elif r.kind == 30:
            need(r.error == 0 and r.b == READ_WINDOW and r.c == READ_WINDOW, "partial read")
            original.append((r.begin, r.ns))
            total_reads[group_of(r.call, r.layer)] += 1
        elif r.kind == 1:
            need(r.call not in calls and r.begin <= r.ns, "native call begin")
            calls[r.call] = r.begin
        elif r.kind == 2:
            need(r.ns >= calls[r.call], "native call return")
            elapsed["prefill" if r.call == 1 else "decode"] += r.ns - calls[r.call]
    need(
        len(ends) == 1325 and len(set(s[:2] for s in ends)) == 38 and len(calls) == 33,
        "C292 site/call denominator",
    )
    need(
        len(deadlines) <= sum(map(len, reserve.values())) == len(original),
        "all reservations served",
    )
    owners = defaultdict(set)
    for i, r in enumerate(rows):
        site = r.call, r.tile, r.layer
        if r.kind == 11:
            prior = owners[r.layer]
            if r.a >= 0:
                need(r.a in prior, "old owner")
                prior.remove(r.a)
            need(r.expert not in prior, "new owner collision")
            prior.add(r.expert)
        if r.kind == 33 and i == ends[site][0]:
            offers, dropped = M["choose"](predictions[site].values(), owners[r.layer], None)
            eligible[site] = offers, dropped
    totals = defaultdict(Counter)
    sites = []
    for site, (index, release) in sorted(ends.items(), key=lambda item: item[1][0]):
        c, _, layer = site
        group = group_of(c, layer)
        count = totals[group]
        all_ids, dropped = eligible[site]
        four = all_ids[:4]
        truth = {e for ids in actual[site].values() for e in ids}
        count.update(
            sites=1,
            predicted_rows=len(predictions[site]),
            resident_excluded=dropped,
            all_after_filter=len(all_ids),
            offers=len(four),
            offered_unused=len(set(four) - truth),
        )
        origins = {}
        for k, (i, wave) in reserve[site].items():
            if k not in deadlines:
                continue
            consumer, ds = deadlines[k]
            need(consumer[:3] == site and 0 <= consumer[3] - wave <= 1, "foreign consumer")
            expert = k[-1]
            if i > index and expert not in origins:
                origins[expert] = (ds, wave, consumer[3])
        matched = {}
        for expert in all_ids:
            if expert not in origins:
                continue
            ds, w, first_w = origins[expert]
            need(min(ds) >= release, "deadline before offer")
            state = look[(*site, first_w)][expert]
            count["uncapped_matched"] += 1
            count["uncapped_at_lookup_" + ("absent", "loading", "ready")[state]] += 1
            if expert in four:
                matched[expert] = ds
                count["first_demand_next_wave" if w != first_w else "first_demand_same_wave"] += 1
                count["top4_at_lookup_" + ("absent", "loading", "ready")[state]] += 1
        count.update(
            matched=len(matched),
            false_offers=len(four) - len(matched),
            routed_without_new_read=len((set(four) & truth) - matched.keys()),
        )
        sites.append((index, release, group, four, matched))
    for group, t in totals.items():
        need(
            t["sites"] == join["totals"][group]["sites"]
            and t["false_offers"] == t["offered_unused"] + t["routed_without_new_read"]
            and t["uncapped_at_lookup_absent"]
            <= join["totals"][group]["available_at_lookup_absent"],
            "classification or lookup population",
        )
        t["false_offer_read_bytes"] = t["false_offers"] * READ_WINDOW
    return sites, totals, original, total_reads, elapsed, len(deadlines)


def run(family_path, review_path):
    for f, digest in (
        (HERE / "protocol.md", RULES),
        (
            HERE.parent / "join.py",
            "858742fc997399ccd0e0bc3e2c3437697bce5aad659337f1141b575ba3d36811",
        ),
        (DEMAND / "score.py", W["PARENT"]),
        (
            DEMAND / "deadlines/score.py",
            "00edc903f5ad2c97d258f3b7727fc72a9ca6624c44bc121fe94a12694a971ef8",
        ),
    ):
        need(sha(f) == digest, "frozen source " + f.name)
    family = read(family_path / "receipt.json", FAMILY)
    reviewed = read(review_path, REVIEW)
    need(
        family["status"] == "PASS_C292_ROUTER_LOOKAHEAD_NUMERIC"
        and reviewed["status"] == "REPRODUCED_C292_ROUTER_LOOKAHEAD"
        and reviewed["family_sha256"] == FAMILY,
        "incomplete independent grade",
    )
    arm = family_path / "overlay_on"
    link = family["arms"]["overlay_on"]["receipt_sha256"]
    receipt = read(arm / "receipt.json", link)
    prior = reviewed["arms"]["overlay_on"]
    need(
        prior["arm_sha256"] == link
        and prior["journal"] == receipt["journal"]
        and receipt["journal"]["sha256"] == JOURNAL
        and receipt["journal_enabled"]
        and receipt["cleanup"],
        "wrong completed observer or journal",
    )
    rows, head = M["AUDIT"]["read_journal"](arm / "raw/phase.pfj1")
    need(
        head["journal_sha256"] == JOURNAL and head["records"] == 102678 and head["flags"] == 1,
        "journal",
    )
    join = JOIN["audit"](rows, True)
    need(
        join == receipt["journal"]["join"] and join["eligible_absent_generations"] == 1803,
        "new E33/34/route join does not match independent review",
    )
    sites, totals, spans, native, elapsed, used_gens = gather(rows, join)
    clock, used = available_clock(spans)
    need(used == M["AUDIT"]["union_ns"](spans), "read union")
    schedules = {}
    for policy, batch in (
        ("all", sites),
        ("prefill_cpu", [s for s in sites if s[2] == "prefill/CPU"]),
    ):
        results = {}
        for regime, b in (("all_bandwidth", batch), ("outside_native_reads", retime(batch, clock))):
            evaluated = W["evaluate"](b, RATE)
            results[regime] = {
                k: evaluated[k]
                for k in ("sites_overlapping_previous_deadlines", "global", "by_target")
            }
        schedules[policy] = results
        for cut in W["CUTS"]:
            for cls in ("fifo", "oracle"):
                k = cut + "_" + cls
                need(
                    results["outside_native_reads"]["global"][k]
                    <= results["all_bandwidth"]["global"][k],
                    "more completions after deleting capacity",
                )
        need(
            results["all_bandwidth"]["global"]["offers"] == sum(len(s[3]) for s in batch),
            "FIFO dropped reservations",
        )
    hosts = {g: join["spans"][g + "/start_to_last_available_ns"]["sum"] for g in totals}
    return {
        "status": "REPRODUCED_C292_MEASURED_PROPOSAL_WINDOWS",
        "source_sha256": sha(Path(__file__)),
        "protocol_sha256": RULES,
        "family_sha256": FAMILY,
        "arm_sha256": link,
        "review_sha256": REVIEW,
        "journal_sha256": JOURNAL,
        "journal_rows": head["records"],
        "sites": len(sites),
        "observed_pack_reads": native,
        "observed_prefetches": 0,
        "distinct_served_and_demanded_generations": used_gens,
        "read_union_ns": used,
        "read_worker_ns": sum(b - a for a, b in spans),
        "on_native_call_wall_ns": elapsed,
        "on_model_process_s": prior["model_s"],
        "off_model_process_s": reviewed["arms"]["overlay_off"]["model_s"],
        "observed_host_e32_to_last_e33_ns": hosts,
        "old_uncapped_at_absent_lookup": 1803,
        "decisions": totals,
        "window_bytes": READ_WINDOW,
        "rate_Bps": RATE,
        "schedules": schedules,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "review-receipt", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.family, a.review_receipt)
    except (ValueError, OSError, KeyError, StopIteration) as e:
        result = {"status": "FAIL_PRESERVED", "error": type(e).__name__, "reason": str(e)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(result["status"])
    raise SystemExit(int(result["status"] != "REPRODUCED_C292_MEASURED_PROPOSAL_WINDOWS"))
