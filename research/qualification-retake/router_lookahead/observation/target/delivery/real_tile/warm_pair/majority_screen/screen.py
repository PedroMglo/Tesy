"""Regrade strict position-majority offers against the sealed C292 prefill generations."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TILE = HERE.parents[1]
WINDOWS = HERE.parents[3] / "numeric/windows"
LATER = TILE / "next_pair/later_tiles/select_pair.py"
OLD = run_path(str(LATER))
P, IO, sha, need, blob = OLD["P"], OLD["OLD"], OLD["sha"], OLD["need"], OLD["blob"]
WIN = run_path(str(WINDOWS / "screen.py"))
W = WIN["W"]
KEY = WIN["M"]["AUDIT"]["identity"]
WIDTH = WIN["READ_WINDOW"]
POLICIES = ("off", "fixed", "majority", "warm_only")
STATES = ("cold", "partial", "full")
RATE = 4_500_000_000
PINS = {
    HERE / "protocol.md": "28dacae7c2d0c9e3efbd3186a9fb5535b4fa1d6e54aa7c66dc542db0c8e4ade7",
    LATER: "a127f3832e67b41173bd1a75d43a4301c5b757f8ffe33b7b1e0b9885ef56097f",
    TILE
    / "next_pair/screen.py": "1ef2d37e5a374b3a6635a9adbd1113641b7330ac8b2611bf65948fb0bad65c81",
    TILE / "prepare.py": "884dbe4ac3347fb003357647ae4bf32cb45cb4ee9e25109f5b29bb3c0219c0a8",
    TILE / "result.json": "ba30c5ccccc3f3ea0729741583bda5ab1a1bdd6e89cfbe79e069a60228319c6c",
    HERE.parent / "result.json": "ec21431749fbc8c64edae2299c3a4810f4351166f4b66963a4079a185469de3c",
    WINDOWS / "screen.py": "ee57b0237502b7569f39c937c672433438482fba3f3d12f06115e87e4bc5e809",
    WINDOWS / "receipt.json": "99ae0a8f90275caf122117cbc1acb466e84ffaa5426370380bbc9c05fc092701",
    WIN["DEMAND"]
    / "deadlines/score.py": "00edc903f5ad2c97d258f3b7727fc72a9ca6624c44bc121fe94a12694a971ef8",
}
COUNT_FIELDS = (
    "sites positions official_reservations eligible_generations eligible_keys predicted_keys "
    "predicted_eligible_keys with_offers with_hit offered matches false unused routed_no_new_read "
    "same_wave next_wave origin_demand origin_preload lookup_absent lookup_loading lookup_ready "
    "offered_before_barrier observed_read_by_barrier observed_publication_by_barrier "
    "observed_publication_by_resume offered_bytes excess_bytes"
).split()


def decision(predicted, occupied):
    need(
        predicted
        and all(
            len(q) == len(set(q)) == 4 and all(type(e) is int and 0 <= e < 128 for e in q)
            for q in predicted
        ),
        "invalid E33 quartet",
    )
    votes = Counter(e for q in predicted for e in q)
    absent = sorted(votes.keys() - occupied, key=lambda e: (-votes[e], e))
    fixed = absent[:4]
    majority = [e for e in fixed if 2 * votes[e] > len(predicted)]
    return votes, absent, fixed, majority


def read_closed(part, io):
    for f, digest in PINS.items():
        need(sha(f.read_bytes()) == digest, "frozen evidence: " + str(f.name))
    _, member = IO["archive"](io, part, P["PART116"])
    raw_fam = member(P["C292"] + "/receipt.json")
    raw_review = member("tesy-lookahead-c292-review-20261125-r01/receipt.json")
    raw_arm = member(P["C292"] + "/overlay_on/receipt.json")
    arm, fam, rev = map(json.loads, (raw_arm, raw_fam, raw_review))
    need(
        sha(raw_fam) == P["FAMILY"] == rev["family_sha256"]
        and sha(raw_review) == P["REVIEW"]
        and fam["status"] == "PASS_C292_ROUTER_LOOKAHEAD_NUMERIC"
        and rev["status"] == "REPRODUCED_C292_ROUTER_LOOKAHEAD",
        "sealed family and review",
    )
    need(
        sha(raw_arm)
        == fam["arms"]["overlay_on"]["receipt_sha256"]
        == rev["arms"]["overlay_on"]["arm_sha256"]
        and arm["journal"] == rev["arms"]["overlay_on"]["journal"]
        and arm["journal_enabled"]
        and arm["cleanup"],
        "sealed observer",
    )
    data = member(P["C292"] + "/overlay_on/raw/phase.pfj1")
    need(sha(data) == P["PFJ"] == arm["journal"]["sha256"], "journal digest")
    return IO["journal"](data), sha(raw_arm)


def index_rows(rows):
    jobs, lookup, exits = defaultdict(dict), {}, {}
    spans = []
    for i, r in enumerate(rows):
        if r.kind == 30:
            need(r.b == r.c == WIDTH and r.error == 0, "whole native pack window")
            spans.append((r.begin, r.ns))
        if r.call != 1:
            continue
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind in (11, 17, 30) or (r.kind == 12 and r.a != 1):
            j = jobs[KEY(r)]
            need(r.kind not in j, "duplicate native service frontier")
            j[r.kind] = (i, r)
        elif r.kind == 34:
            lookup[(*site, r.expert)] = r.a
        elif r.kind == 20:
            exits[site] = r.ns
    return jobs, lookup, exits, spans


def first_origins(tile, dst, cell, begin, deadlines, index):
    jobs, lookup, exits, _ = index
    origins, eligible = {}, 0
    release = begin.ns
    for r in cell["reserves"]:
        e = r["expert"]
        k = (dst, r["slot"], r["gen"], e)
        j = jobs[k]
        need(set(j) == {11, 12, 17, 30}, "incomplete service generation")
        if e in cell["occupied"] or k not in deadlines or j[11][0] <= cell["last_pred"]:
            continue
        use, ds = deadlines[k]
        need(use[:3] == (1, tile, dst) and release <= min(ds), "foreign use or late release")
        need(0 <= use[3] - r["wave"] <= 1, "reservation to first consumer")
        reason = j[12][1].a
        need(reason in (0, 2), "unexpected enqueue reason")
        read, publish = j[30][1].ns, j[17][1].ns
        state = lookup[(*use, e)]
        need(state in (0, 1, 2) and read <= publish <= exits[use], "service after resume")
        detail = dict(
            key=k,
            deadlines=ds,
            reason=reason,
            wave=r["wave"],
            first_wave=use[3],
            lookup=state,
            read=read,
            publish=publish,
            resume=exits[use],
        )
        origins.setdefault(e, detail)
        eligible += 1
    return origins, eligible


def metrics(offers, base, origins, truth, release):
    c = Counter(base)
    hits = set(offers) & origins.keys()
    c.update(
        with_offers=int(bool(offers)),
        with_hit=int(bool(hits)),
        offered=len(offers),
        matches=len(hits),
        false=len(offers) - len(hits),
        unused=len(set(offers) - truth),
        routed_no_new_read=len(set(offers) & truth - hits),
        offered_bytes=WIDTH * len(offers),
        excess_bytes=WIDTH * (len(offers) - len(hits)),
    )
    for e in hits:
        o = origins[e]
        barrier = o["deadlines"][2]
        c["offered_before_barrier"] += release < barrier
        c["observed_read_by_barrier"] += o["read"] <= barrier
        c["observed_publication_by_barrier"] += o["publish"] <= barrier
        c["observed_publication_by_resume"] += o["publish"] <= o["resume"]
        c["origin_preload" if o["reason"] == 2 else "origin_demand"] += 1
        c["same_wave" if o["wave"] == o["first_wave"] else "next_wave"] += 1
        c[("lookup_absent", "lookup_loading", "lookup_ready")[o["lookup"]]] += 1
    need(
        c["false"] == c["unused"] + c["routed_no_new_read"]
        and c["matches"] == c["observed_publication_by_resume"],
        "attribution",
    )
    return c


def clock_grades(batches, clock):
    schedules = {}
    for name, batch in batches.items():
        need([b[0] for b in batch] == sorted(set(b[0] for b in batch)), "natural offer order")
        modes = {}
        for mode, data in (
            ("all_bandwidth", batch),
            ("outside_native_reads", WIN["retime"](batch, clock)),
        ):
            result = W["evaluate"](data, RATE)
            wanted = (
                "sites",
                "offers",
                "hits",
                "reserve_fifo",
                "accept_or_barrier_fifo",
                "barrier_fifo",
            )
            modes[mode] = {
                group: {k: vals.get(k, 0) for k in wanted}
                for group, vals in {"all": result["global"], **result["by_target"]}.items()
            }
        schedules[name] = modes
    return schedules


def evaluate(rows):
    sites, tiles = OLD["collect"](rows)
    deadlines = W["job_deadlines"](rows)
    index = index_rows(rows)
    clock, _ = WIN["available_clock"](index[-1])
    totals = {p: defaultdict(Counter) for p in POLICIES}
    batches = {p: [] for p in POLICIES}
    private, qualifying, all_hits = [], [], []
    for tile, (n, start, end, _) in tiles.items():
        for dst in range(1, 25):
            cell = sites[tile, dst]
            release = rows[cell["last_pred"]]
            need(release.kind == 33 and len(cell["pred"]) == len(cell["ranks"]) == n, "tile rows")
            truth = {e for q in cell["ranks"] for e in q}
            need(truth == {e for _, e, _, _ in cell["demands"]}, "E27 vs E10 authority")
            occupied = cell["occupied"]
            state = "full" if len(occupied) == 40 else "partial" if occupied else "cold"
            votes, absent, fixed, strict = decision(cell["pred"], occupied)
            selected = dict(
                off=[], fixed=fixed, majority=strict, warm_only=strict if state == "full" else fixed
            )
            origins, eligible = first_origins(tile, dst, cell, release, deadlines, index)
            base = dict(
                sites=1,
                positions=n,
                official_reservations=len(cell["reserves"]),
                eligible_generations=eligible,
                eligible_keys=len(origins),
                predicted_keys=len(absent),
                predicted_eligible_keys=len(set(absent) & origins.keys()),
            )
            row = dict(
                tile=tile,
                positions=[start, end],
                destination=dst,
                width=n,
                occupancy=len(occupied),
                state=state,
                votes=[[e, votes[e]] for e in fixed],
                fixed=fixed,
                majority=strict,
                matching=[{"expert": e, **origins[e]} for e in fixed if e in origins],
            )
            private.append(row)
            scored = {}
            for name, offers in selected.items():
                c = metrics(offers, base, origins, truth, release.ns)
                scored[name] = c
                for group in ("all", state, str(n), f"{state}/{n}"):
                    totals[name][group].update(c)
                matched = {e: origins[e]["deadlines"] for e in offers if e in origins}
                batches[name].append(
                    (cell["last_pred"], release.ns, f"{state}/{n}", offers, matched)
                )
            s, f = scored["majority"], scored["fixed"]
            if state == "full" and s["matches"] and s["false"] < f["false"]:
                qualifying.append((tile, dst))
                if s["matches"] == f["matches"]:
                    all_hits.append((tile, dst))
    outputs = {}
    groups = ["all", *STATES, "32", "29", *(f"{s}/{n}" for s in STATES for n in (32, 29))]
    for policy, counts in totals.items():
        outputs[policy] = {g: {k: counts[g][k] for k in COUNT_FIELDS} for g in groups}
    schedules = clock_grades(batches, clock)
    return private, outputs, schedules, qualifying, all_hits


def short(row):
    return {
        k: row[k]
        for k in ("tile", "destination", "width", "occupancy", "votes", "fixed", "majority")
    } | {
        "matched_fixed": [d["expert"] for d in row["matching"]],
        "matched_majority": [
            d["expert"] for d in row["matching"] if d["expert"] in row["majority"]
        ],
    }


def run(part, io):
    rows, arm_sha = read_closed(part, io)
    private, counts, schedules, qualified, all_hits = evaluate(rows)
    prior = json.loads((WINDOWS / "receipt.json").read_bytes())
    old = prior["decisions"]["prefill/CPU"]
    fixed = counts["fixed"]["all"]
    for a, b in (
        ("offered", "offers"),
        ("matches", "matched"),
        ("false", "false_offers"),
        ("next_wave", "first_demand_next_wave"),
        ("same_wave", "first_demand_same_wave"),
        ("sites", "sites"),
        ("positions", "predicted_rows"),
        ("predicted_keys", "all_after_filter"),
        ("predicted_eligible_keys", "uncapped_matched"),
    ):
        need(fixed[a] == old[b], "fixed control: " + a)
    for mode, grade in schedules["fixed"].items():
        need(
            all(
                prior["schedules"]["prefill_cpu"][mode]["global"][k] == v
                for k, v in grade["all"].items()
            ),
            "fixed deadline control",
        )
    by_site = {(r["tile"], r["destination"]): r for r in private}
    need(len(by_site) == 144 and fixed["matches"] == 421 and fixed["offered"] == 562, "population")
    io.emit("sites.json", blob(private))
    return dict(
        status="REPRODUCED_C292_PREFILL_CPU_MAJORITY",
        site_count=len(by_site),
        protocol_sha256=PINS[HERE / "protocol.md"],
        program_sha256=sha(Path(__file__).read_bytes()),
        provenance=dict(
            manifest=P["PART116"],
            family=P["FAMILY"],
            review=P["REVIEW"],
            journal=P["PFJ"],
            arm=arm_sha,
            baseline=PINS[WINDOWS / "receipt.json"],
        ),
        sites_sha256=io.files["sites.json"],
        hot_discriminants=len(qualified),
        hot_discriminants_preserving_all_hits=len(all_hits),
        qualifying_by_width=dict(Counter(str(by_site[k]["width"]) for k in qualified)),
        first_hot_discriminant=short(by_site[qualified[0]]) if qualified else None,
        decision="SCOPED_OPPORTUNITY_NO_TIME_CREDIT"
        if qualified
        else "NO_WARM_SITE_RETAINS_A_HIT_WITH_LESS_SURPLUS",
        paid_sites=[short(by_site[k]) for k in ((1, 1), (5, 1))],
        counts=counts,
        schedules=schedules,
        window_bytes=WIDTH,
        rate_Bps=RATE,
        model_launches=0,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part116", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    io = P["Inputs"](args.new_output_dir)
    try:
        result = run(args.part116, io)
    except Exception as error:
        result = dict(status="FAIL_PRESERVED", error=type(error).__name__, reason=str(error))
    io.emit("receipt.json", blob(result))
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
