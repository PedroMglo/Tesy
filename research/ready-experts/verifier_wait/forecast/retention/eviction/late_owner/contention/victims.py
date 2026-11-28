"""Combine a past-only victim policy with independently defined peer service credits."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(HERE / "frontier.py")
C, need, sha, save = (F[k] for k in ("C", "need", "sha", "save"))
TIER = HERE.parents[5] / "layer/prefix/wave"
T = run_path(TIER / "tier_bank.py")
OLD = "14ad307b2b131479ebadbb9cd64247a83971fa16ef4a406d6feeb414585eedbf"
SERVICE = "2793888c234dd8f096c8d434b09d8de43042794370d232d4727a5f7fa2ea6dc2"
METHOD = "68cef6ae8e9545b2ef9ebfe565126e124d2f6904d1b236d558670b4ec99fa864"
PPM = 1_000_000


def sources():
    folder = TIER / "evidence-tier-20261128-r01"
    old = F["SRC"]["pinned"](folder / "receipt.json", OLD)
    path = folder / "transactions.json.gz"
    need(
        sha(path) == old["transactions_sha256"]
        and sha(TIER / "tier_bank.py") == old["source_sha256"],
        "tier inputs",
    )
    w = F["unpack"](path)
    freq = Counter({(layer, expert): n for layer, expert, n in w["counts"]})
    tx = w["reservations"]
    need(sum(freq.values()) == 5727 and T["quotas"](freq) == [252, 101], "causal quotas")
    effect, info = T["run_order"](
        tx, w["initial"], list(map(tuple, w["seed"])), freq, [252, 101], False
    )
    digest = hashlib.sha256(json.dumps(effect, separators=(",", ":")).encode()).hexdigest()
    need(
        info == old["result"]["partition"] and digest == old["result"]["witness_sha256"],
        "renewable ownership",
    )
    return tx, effect


def eligible(rows, hits):
    events = defaultdict(lambda: (set(), set()))
    for i, r in enumerate(rows, 1):
        events[r[5]][1].add(i)
        events[r[6]][0].add(i)
    live = set()
    previous = None
    clips = Counter()
    any_peers = set()
    quartet_wall = any_wall = 0
    for t, (stop, start) in sorted(events.items()):
        if previous is not None:
            width = t - previous
            hit_live = live & hits
            other = live - hits
            if hit_live and other:
                any_wall += width
                any_peers.update(other)
                if (
                    len(other) == 3
                    and len(hit_live) == 1
                    and len({tuple(rows[i - 1][1][:3]) for i in live}) == 1
                ):
                    quartet_wall += width
                    for i in other:
                        clips[i] += width
        need(
            stop <= live and not start & live and len(live) <= 4, "positive service or worker count"
        )
        live.difference_update(stop)
        live.update(start)
        previous = t
    need(not live and sum(clips.values()) == 3 * quartet_wall, "peer-time conservation")

    def duration(i):
        return rows[i - 1][6] - rows[i - 1][5]

    whole = {i: duration(i) for i in clips}
    full = {i: duration(i) for i in any_peers}
    need(
        all(0 < w <= whole[i] for i, w in clips.items()) and whole.keys() <= full.keys(),
        "nested supports",
    )
    return dict(clipped=dict(clips), whole_quartet=whole, any_peer=full), dict(
        quartet_wall_ns=quartet_wall,
        any_mixed_wall_ns=any_wall,
        clipped_worker_ns=sum(clips.values()),
    )


def budget(clock):
    return min(10**10 - clock["granted_first_ns"], C["B"]["DECODE_LIMIT"] - clock["decode"])


def line(price):
    end = price(PPM)
    if budget(end) < 0:
        return dict(full=end, decision="NO_GO_FREE_ELIGIBLE_READ")
    zero = price(0)
    lo, hi = -1, PPM
    if budget(zero) >= 0:
        hi = 0
    else:
        lo = 0
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if budget(price(mid)) >= 0:
                hi = mid
            else:
                lo = mid
    at = budget(price(hi))
    before = budget(price(hi - 1)) if hi else None
    need(at >= 0 and (before is None or before < 0), "adjacent ppm endpoints")
    return dict(
        full=end,
        decision="HEADROOM_ONLY",
        min_reduction_ppm=hi,
        margin_at_ns=at,
        preceding_margin_ns=before,
    )


def priced_case(arm, hits, placed, tag, amounts):
    def price(ppm):
        cut = {i: v * ppm // PPM for i, v in amounts.items()}
        return F["clock"](F["adjusted"](arm, cut), hits, placed, False, tag)

    return line(price)


def evaluate(folder):
    need(
        sha(HERE / "victims-protocol.md") == METHOD and sha(folder / "service.json.gz") == SERVICE,
        "frozen service and protocol",
    )
    basis, _, _ = F["freeze"]()
    data = F["unpack"](folder / "service.json.gz")
    tx, effect = sources()
    phases = defaultdict(Counter)
    hits = set()
    for i, ((call, _, layer, *_), (tier, source, dest)) in enumerate(
        zip(tx, effect, strict=True), 1
    ):
        need(tier == int(layer >= 25), "tier selection")
        p = phases[C["phase"](call)]
        p["jobs"] += 1
        if source is None:
            p["requested_from_NVMe_B"] += F["WINDOW"]
        else:
            hits.add(i)
            p["hits"] += 1
        if dest is not None:
            p["captures"] += 1
            p["cuda_victim_payload_B" if tier else "cpu_victim_payload_B"] += T["PAYLOAD"]
        if tier:
            p["host_to_cuda_primary_payload_B"] += T["PAYLOAD"]
    need(len(hits) == 674 and sum(p["jobs"] for p in phases.values()) == 2354, "conservation")
    result = {}
    for tag, raw in data.items():
        arm, rows = basis["arms"][tag], raw["jobs"]
        F["verify_jobs"](rows, arm)
        for (c, t, layer, s, g, e, _), job in zip(tx, rows, strict=True):
            need(
                job[0] == [layer, s, g, e] and job[1][:3] == [c, t, layer],
                "wrong generation or consumer",
            )
        credit, share = eligible(rows, hits)
        modes = {}
        by_phase = {}
        for key, amounts in credit.items():
            census = defaultdict(Counter)
            for i, v in amounts.items():
                p = census[C["phase"](rows[i - 1][1][0])]
                p.update(peers=1, eligible_worker_ns=v)
            by_phase[key] = census
        for name, placed in (("paid", False), ("favorable", True)):
            baseline = F["clock"](arm, hits, placed, False, tag)
            cases = {
                mode: priced_case(arm, hits, placed, tag, amounts)
                for mode, amounts in credit.items()
            }
            chain = [baseline, *(cases[k]["full"] for k in credit)]
            need(
                all(
                    a["granted_first_ns"] >= b["granted_first_ns"] and a["decode"] >= b["decode"]
                    for a, b in zip(chain, chain[1:], strict=False)
                ),
                "nonmonotone composition",
            )
            modes[name] = dict(baseline=baseline, cases=cases)
        exposed = Counter()
        ids = {tuple(j[0]): i for i, j in enumerate(rows, 1)}
        for _, _, _, keys in raw["last"]:
            last = {ids[tuple(k)] for k in keys}
            exposed.update(
                barriers=1,
                any_last_hit=int(bool(last & hits)),
                any_last_quartet_peer=int(bool(last & credit["clipped"].keys())),
                any_last_mixed_peer=int(bool(last & credit["any_peer"].keys())),
            )
        result[tag] = dict(modes=modes, eligible=by_phase, intervals=share, consumers=exposed)
    joint = {}
    for name in ("paid", "favorable"):
        joint[name] = {}
        for case in ("clipped", "whole_quartet", "any_peer"):
            both = [v["modes"][name]["cases"][case] for v in result.values()]
            headroom = min(budget(b["full"]) for b in both)
            row = dict(
                full_margin_ns=headroom, decision="NO_GO" if headroom < 0 else "GO_COST_FIXTURE"
            )
            if headroom >= 0:
                row["min_reduction_ppm"] = max(b["min_reduction_ppm"] for b in both)
            joint[name][case] = row
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        method=METHOD,
        service=SERVICE,
        old_bank=OLD,
        phases=phases,
        arms=result,
        joint=joint,
        http_requests=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--service", type=Path, required=True)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        result = evaluate(a.service)
        if a.check:
            need(json.loads(a.check.read_bytes()) == result, "changed composition")
        else:
            save(a.new_output_dir / "victims.json", result)
        print(result["joint"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
