"""Combine sealed T1 banks with compatible prefill reads and individually timed decode steps."""

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ENV = run_path(str(HERE / "envelope.py"))
HTTP, AUDIT, G, need, save = (ENV[k] for k in ("HTTP", "AUDIT", "G", "need", "save"))
SLOT = run_path(str(HERE.parent / "slots.py"))
B = SLOT["B"]
MIX = run_path(str(B["TRACE"] / "prefill_retention/mixed_bank/score.py"))
METHOD = "2dd9af66f33ad7b9fd79831b44a92164907321e4149e494dcd55cd31b3fb4fcd"
ENVELOPE = "1d19912281e2ca9502bd00c7587d18c50e246aa7a3cb3c96c6ec91cd2f0aa35f"
BANKS = "ef8a45e879514fb5081e24205236c37124102cc4ba522cd2e09476a1f223e12b"
RATE = ENV["IO"]["RATE"]
WINDOW = B["WINDOW"]


def generations(a, reference, schedule):
    data, original = HTTP["R"]["cases"](a)
    tiers = prior = None
    for name in ("P106", "P97"):
        rows, tiers, ids = B["trace_arm"](a, name, tiers, data, original)
        need(
            B["account"](rows, tiers) == reference["population"]
            and ids == reference["target_id_digests"],
            "complete jobs, routing and target IDs",
        )
        _, calls = B["C"]["timeline"](rows)
        initial, waves, _ = SLOT["gather"](rows)
        epochs, uses = SLOT["lifetimes"](initial, waves)
        all_reloads, edges = SLOT["borrowers"](waves, epochs, uses)
        chosen, _ = SLOT["matching"](edges)
        fixed = {tuple(s["target"]): tuple(s["carrier"]) for s in schedule["matched"]["schedule"]}
        need(
            chosen == fixed
            and len(all_reloads) * WINDOW == reference["population"]["total"]["aligned_bytes"]
            and len(fixed) * WINDOW == schedule["aligned_reads_avoided_bytes"],
            "same prefill schedules",
        )
        snapshot = ({k: v[0] for k, v in calls.items()}, set(all_reloads), set(chosen))
        if prior is not None:
            need(snapshot == prior, "same generations and call bindings in both processes")
        prior = snapshot
    return prior


def selection(a, previous):
    name, pin, _ = B["C"]["SOURCES"]["P106"]
    root = a.archive / "part-106" / name
    sealed, _, _, _ = B["Q"]["read_new"](root, pin)
    result = {"empty": set()}
    for name, bank in MIX["select"](root / "ON/observer/events.pfj", sealed).items():
        keys = list(bank.held)
        reference = previous["T1"][name]
        digest = hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()
        need(
            digest == reference["selected_sha256"]
            and len(keys) == MIX["CAP"]
            and all(reference[k] == v for k, v in bank.summary().items()),
            "sealed T1 selector, acquisition and exact ordered membership",
        )
        result[name] = set(keys)
    return result


def exposed(steps, ppm):
    early = late = 0
    for hits, duration_ns, before in steps:
        # B / (B/s) converted to ns, times the ppm exposure, rounded up.
        saved = min(duration_ns, (hits * WINDOW * ppm * 1000 + RATE - 1) // RATE)
        if before:
            early += saved
        else:
            late += saved
    return early, early + late


def fractions(steps, early_required, total_required):
    def fits(ppm):
        early, total = exposed(steps, ppm)
        return early >= early_required and total >= total_required

    best = None
    if fits(1_000_000):
        lo, hi = 0, 1_000_000
        while lo < hi:
            mid = (lo + hi) // 2
            if fits(mid):
                hi = mid
            else:
                lo = mid + 1
        best = lo
        need(fits(best) and (best == 0 or not fits(best - 1)), "minimum passing ppm")
    before, total = exposed(steps, 1_000_000)
    return dict(
        minimum_exposed_ppm=best,
        required_early_ns=early_required,
        required_total_ns=total_required,
        max_early_ns=before,
        max_decode_ns=total,
        still_missing_early_ns=max(0, early_required - before),
        still_missing_decode_ns=max(0, total_required - total),
    )


def fixture():
    # All service available after first final can pay decode but cannot pay an earlier deadline.
    steps = [(0, 2000, True), (10, 3000, False)]
    need(
        exposed(steps, 0) == (0, 0)
        and exposed(steps, 1_000_000) == (0, 3000)
        and fractions(steps, 1, 100)["minimum_exposed_ppm"] is None
        and fractions(steps, 0, 100)["minimum_exposed_ppm"] is not None,
        "cut and capped service",
    )
    prefill, bank, repeats = {1, 2, 3, 4}, {1, 3}, {2, 3}
    need(len((prefill & bank) | repeats) == 3 and len(bank & repeats) == 1, "double credit")
    return True


def compare(path, bank, prefill, savings, calls, marks, cut):
    held = {k for k, c in calls.items() if (k[0], k[3]) in bank}
    bank_pre = held & prefill
    decode_hits = Counter(calls[k] for k in held - prefill)
    steps = []
    covered = set()
    for e in path["groups"]:
        start, end = e["start"], e["end"]
        span = set(range(start + 3, end + 3))
        need(not (span & covered), "no overlapping decode interval")
        covered.update(span)
        if not e["block"]:
            need(end == start + 1, "one preserved native step")
            series = marks[e["arm"]]
            steps.append((decode_hits[start + 3], (series[end] - series[start]) * 1000, end <= cut))
    need(covered == set(range(3, 49)), "all 46 decode calls including EOG")
    remaining = path["conditional_prefill_service"]["minimum_bytes_removed"]
    total_ns = int(Decimal(str(path["more_decode_s_to_six"])) * 10**9)
    results = {}
    for label, extra in savings.items():
        overlap = len(bank_pre & extra)
        union = len(bank_pre | extra)
        needed = remaining - union * WINDOW
        early_ns = max(0, needed) * 10**9 // RATE
        results[label] = dict(
            bank_prefill=len(bank_pre),
            overlap=overlap,
            union=union,
            avoided_aligned_bytes=union * WINDOW,
            extra_required_prefill_bytes_before_decode_credit=needed,
            **fractions(steps, early_ns, total_ns),
        )
    return dict(
        serial_calls=len(steps),
        early_calls=sum(t[2] for t in steps),
        eligible_decode_hits=sum(t[0] for t in steps),
        eligible_early_hits=sum(h for h, _, early in steps if early),
        excluded_hits_in_block_calls=sum(decode_hits.values()) - sum(t[0] for t in steps),
        prefill=results,
    )


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit and AUDIT["sha"](HERE / "bank-protocol.md") == METHOD,
        "frozen composition",
    )
    e = G["read"](HERE / "envelope-result.json", ENVELOPE)
    previous = G["read"](MIX["HERE"] / "receipt.json", BANKS)
    reference = G["read"](HERE.parent / "reload-result.json", ENV["RELOADS"])
    schedule = G["read"](HERE.parent / "slot-result.json", ENV["SLOTS"])
    review = G["read"](HERE / "http-result.json", e["four_arm_review_sha256"])
    HTTP["R"]["reopen"](a.family, review["family_sha256"])
    control = fixture()
    calls, rereads, matched = generations(a, reference, schedule)
    banks = selection(a, previous)
    prefill = {k for k, c in calls.items() if c <= 2}
    need(
        len(prefill) == 1263
        and sum(c == 1 for c in calls.values()) == 51
        and matched <= rereads <= prefill,
        "prefill calls and nesting",
    )
    savings = {"no_rescue": set(), "matched35": matched, "all230": rereads}
    marks = {}
    cut = e["turns"]["T2"]["first_final_sample"] - 1
    for mode in ("FILTER", "FIXED", "SERIAL"):
        marks[mode], boundary = AUDIT["ticks"](a.family / mode, 2)
        need(boundary == cut == 44 and len(marks[mode]) == 47, "first final and EOG")
    scenarios = {}
    for label, keys in banks.items():
        all_hits = {k for k in calls if (k[0], k[3]) in keys}
        if label != "empty":
            counted = Counter(
                (B["C"]["phase"](calls[k]), "CPU" if k[0] < 25 else "CUDA0") for k in all_hits
            )
            for name in ("P97", "P106"):
                for phase, group in previous["T2"][name][label]["volumes"].items():
                    need(
                        all(counted[phase, tier] == stats["hits"] for tier, stats in group.items()),
                        "historical reservations supplied by T1",
                    )
        paths = {}
        for kind, family in e["turns"]["T2"]["scenarios"].items():
            records = []
            for witness in family["witnesses"]:
                score = compare(witness, keys, prefill, savings, calls, marks, cut)
                if label == "empty":
                    service = witness["conditional_prefill_service"]
                    for s, k in (
                        ("matched35", "remaining_after_matched_signed_bytes"),
                        ("all230", "remaining_after_all_reloads_signed_bytes"),
                    ):
                        need(
                            score["prefill"][s]["extra_required_prefill_bytes_before_decode_credit"]
                            == service[k]
                            and score["eligible_decode_hits"] == 0,
                            "empty bank ablation",
                        )
                records.append(score)
            paths[kind] = records
        scenarios[label] = dict(
            held=len(keys),
            held_payload_bytes=len(keys) * B["PAYLOAD"],
            serial_peak_plus_bank_payload_bytes=review["arms"]["SERIAL"]["maxima"]["cgroup_peak_bytes"]
            + len(keys) * B["PAYLOAD"],
            acquisition_B={"CPU": 0, "CUDA0": 0}
            if label == "empty"
            else previous["T1"][label]["acquisition_B"],
            witnesses=paths,
        )
    return dict(
        status="TRACE_DERIVED_T1_BANK_AND_PRICED_BLOCKS",
        commit=commit,
        tree=tree,
        method_sha256=METHOD,
        envelope_sha256=ENVELOPE,
        banks_sha256=BANKS,
        prefill_generations=len(prefill),
        decode_generations=len(calls) - len(prefill),
        aligned_read_bytes=WINDOW,
        rate_Bps=RATE,
        serial_cap_bytes=20 << 30,
        controls_passed=control,
        new_model_starts=0,
        new_requests=0,
        scenarios=scenarios,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "family", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    save(args.new_output_dir / "result.json", study(args))
