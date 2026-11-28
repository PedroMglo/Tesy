"""Bind the independent CPU0 journals to compact worker schedules and target rank views."""

from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LAYER = HERE.parent
PARENT = "57d3f824e29912dce5d3fdeb8e273775d34c5c8075b798b3d10f03bd88ce2cf5"
METHOD = "83a3bbca27ab306a1dcdb7e4b1d7a4961255a2fc0529e36eee4d8a34b26f0168"
CASES = ("decode4", "prefill9")
JOURNALS = ("P97", "P106")
SITES = {"decode4": [11, 1, 0, -1], "prefill9": [2, 5, 0, 2]}


def need(value, why):
    if not value:
        raise ValueError(why)


def role_names(case, regime, scenario):
    chosen = [j["expert"] for j in scenario["jobs"] if j["hit"]] if case == "decode4" else [63]
    return (["DISK"] if regime == "BANK" else []) + [
        "COPY",
        *("ONE_" + str(e) for e in chosen),
        "ALL",
    ]


def prepare(archive):
    lifetime = run_path(LAYER / "lifetime.py")
    f = lifetime["F"]
    src = f["SRC"]
    decision = src["pinned"](LAYER / "evidence-groups-20261128-r01/decision.json", PARENT)
    need(decision["status"] == "GO_GROUP_SERVICE_FIXTURE", "prospective admission")
    hits = {tuple(s["site"]): set(s["reservation_indexes"]) for s in decision["registered_CPU0"]}
    initial, tx, actions, service, _ = lifetime["inputs"]()
    windows_path = LAYER / "evidence-lifetime-20261128-r01/waves.json.gz"
    need(
        lifetime["sha"](windows_path)
        == "13eeb57a2d1c223ff99ec8ce7de453476b5bb52105b399bd9a5584206f2a538d",
        "consumer projection",
    )
    windows = f["unpack"](windows_path)
    scenarios = {}
    for tag in JOURNALS:
        name, outer, _ = src["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            _, rows, _, _ = src["Q"]["read_new"](root, outer)
            pfj = root / "ON/observer/events.pfj"
        else:
            src["pinned"](root / "family.json", outer)
            pfj = root / "ON/raw/events.pfj"
            rows, _ = src["T"]["PFJ"]["read_journal"](pfj)
        journal = lifetime["sha"](pfj)
        need(
            journal == windows[tag]["journal_sha256"] and f["collect"](rows) == service[tag],
            "whole native service and source clock",
        )
        jobs = service[tag]["jobs"]
        by_key = {tuple(j[0]): i for i, j in enumerate(jobs)}
        scenarios[tag] = {}
        for name, site in SITES.items():
            demands = next(w[3] for w in windows[tag]["cpu"] if w[0] == site)
            by_expert = {k[3]: k for k in demands}
            ranks = [r for r in rows if r.kind == 27 and [r.call, r.tile, r.layer] == site[:3]]
            need(
                [r.b for r in ranks] == list(range(1 if name == "decode4" else 20)),
                "rank positions",
            )
            logical = [list(r.a.to_bytes(4, "little")) for r in ranks]
            view = [[by_expert[e][1] if e in by_expert else -1 for e in row] for row in logical]
            need(
                {e for row in logical for e in row} >= set(by_expert)
                and all(len(set(row)) == 4 for row in logical),
                "active and parked rank coverage",
            )
            indices = sorted(by_key[tuple(k)] for k in demands if tuple(k) in by_key)
            n = len(indices)
            need(
                n == (4 if name == "decode4" else 15)
                and indices == list(range(indices[0], indices[-1] + 1)),
                "complete contiguous native reservation cohort",
            )
            entry = [k for k in demands if tuple(k) not in by_key]
            need(all(initial[tuple(k[:2])] == tuple(k) for k in entry), "initial READY")
            _, barrier, _, last = next(row for row in service[tag]["last"] if row[0] == site)
            zero = min(jobs[i][2] for i in indices)

            selected = []
            for i in indices:
                j = jobs[i]
                _, slot, gen, expert = j[0]
                need(
                    j[1] == ([2, 5, 0, 1] if name == "prefill9" else site)
                    and actions[i][2] == (i in hits[tuple(site)]),
                    "causal source and generation",
                )
                selected.append(
                    dict(
                        index=i,
                        expert=expert,
                        slot=slot,
                        gen=gen,
                        old=tx[i][6],
                        worker=j[3],
                        hit=actions[i][2],
                        reserve_ns=j[2] - zero,
                        dispatch_ns=j[4] - zero,
                        ready_ns=j[6] - zero,
                        published_ns=j[-1] - zero,
                    )
                )
            need(
                len({j["worker"] for j in selected}) == 4
                and [j["dispatch_ns"] for j in selected]
                == sorted(j["dispatch_ns"] for j in selected)
                and len({k[1] for k in demands}) == len(demands)
                and last[0][-1] == (52 if name == "decode4" else 63)
                and len(last) == 1,
                "FIFO and final producer",
            )
            scenarios[tag][name] = dict(
                journal=journal,
                site=site,
                logical=logical,
                view=view,
                demands=demands,
                entry=entry,
                jobs=selected,
                barrier_ns=barrier - zero,
            )
    for name in CASES:
        a, b = (scenarios[t][name] for t in JOURNALS)
        need(
            all(a[k] == b[k] for k in ("logical", "view", "demands", "entry")),
            "same target workload",
        )
    return scenarios
