"""Price compulsory weights when only the current target router has revealed its IDs."""

import argparse
import hashlib
import os
import shutil
import struct
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(HERE / "transport_grade.py")
T, R, need, sha = (G[k] for k in ("T", "R", "need", "sha"))
METHOD = "dc07c3159d449da2d11029eefd9f2e22be02eea5ccae36154e7e4b6af61f5664"
ELF = "192735fc3a186bc7c1c7ce19e5381b9fd23536ec361595c3c7878ab2a77a7945"
PRIOR_BUILD = "7cd69c35c9614003be77b557d170441a794ba47bc15fe129b0d8d6c569c4a36c"
PROTOCOL = HERE / "layer-release-protocol.md"


def sites(obs):
    return [
        (key, list(items))
        for key, items in groupby(enumerate(obs["waves"]), key=lambda item: tuple(item[1][0][:3]))
    ]


def capture(archive, spans):
    s = run_path(HERE / "source.py")
    src = s["SRC"]
    profile = src["Q"]["PROFILE"]
    common, advance = None, {}
    for tag, obs in spans.items():
        arm = archive / ("part-" + tag[1:]) / src["SOURCES"][tag][0] / "ON"
        file = arm / ("raw/events.pfj" if tag == "P97" else "observer/events.pfj")
        need(sha(file) == s["E"][tag], "rank journal")
        if tag == "P97":
            rows, _ = profile["PFJ"]["read_journal"](file)
        else:
            cut, total = profile["metadata"](file, True)
            rows = [
                r._replace(call=r.call - 86) if r.call else r
                for r in profile["iter_rows"](file, cut, total - cut)
            ]
        need(src["NATIVE"]["host_trace"](rows)["route"] == obs["route"], "official route")
        windows = {site: items[0][1] for site, items in sites(obs)}
        ranks = {site: [] for site in windows}
        lag = []
        for r in rows:
            if r.kind != 27:
                continue
            key = r.call, r.tile, r.layer
            first = windows[key]
            need(
                first[0][3] == r.wave and first[1] <= r.ns <= first[2] and r.b == len(ranks[key]),
                "rows not yet observable at first remap",
            )
            ranks[key].append(r.a)
            lag.append(r.ns - first[1])
        words = [[list(k), v] for k, v in ranks.items()]
        need(common is None or common == words, "different target ranks")
        common = words
        advance[tag] = max(lag)
    return common, advance


def regroup(obs, chosen, words):
    digest = hashlib.sha256()
    allowed = {}
    first = {}
    groups = sites(obs)
    need(len(groups) == len(words), "layer census")
    for (site, items), (key, values) in zip(groups, words, strict=True):
        call, tile, layer = site
        need(list(site) == key and site not in allowed, "route order")
        if call == 1:
            pos, n = 2044, 5
        elif call == 2:
            pos, n = 2049 + 32 * (tile - 1), 20 if tile == 5 else 32
        else:
            pos, n = 2197 + call - 3, 1
        expected = n if layer < 35 else int(call > 1 and (call != 2 or tile == 5))
        need(len(values) == expected, "target mask")
        first[site] = items[0][0]
        union = set()
        for i, word in enumerate(values):
            rank = word.to_bytes(4, "little")
            need(max(rank) < 128 and len(set(rank)) == 4, "target top four")
            position = pos + (i if layer < 35 else n - 1)
            digest.update(struct.pack("<5i4B", call, tile, layer, position, i, *rank))
            union.update(rank)
        allowed[site] = union
    need(
        digest.hexdigest() == obs["route"]["sha256"] and sum(len(v) for _, v in words) == 7012,
        "ordered router hash",
    )
    result = []
    for p, i, j, layer, expert in chosen:
        site = tuple(obs["waves"][i][0][:3])
        need(layer == site[2] and expert in allowed[site], "expert not revealed by its router")
        result.append((p, first[site], j, layer, expert))
    return result


def layer_prices(obs, times):
    groups = sites(obs)
    gains = {k: Counter(dict.fromkeys(R["PHASES"], 0)) for k in ("last_barrier", "next_router")}
    exposed = {k: Counter(dict.fromkeys(R["PHASES"], 0)) for k in gains}
    for i, (site, items) in enumerate(groups):
        call = site[0]
        phase = R["phase"](call)
        group, first = items[0]
        start = first[1]
        stop = obs["calls"][call - 1][1]
        if i + 1 < len(groups) and groups[i + 1][0][0] == call:
            stop = groups[i + 1][1][0][1][1]
        last = items[-1][1][3]
        waits = sum(row[3] - row[2] for _, row in items)
        need(start <= last <= stop and 0 <= waits <= last - start, "disjoint router window")
        service = times.get(group, 0)
        for name, end in (("last_barrier", last), ("next_router", stop)):
            rest = end - start - waits
            debt = max(0, service - rest)
            gains[name][phase] += waits - debt
            exposed[name][phase] += debt
    need(
        all(gains["next_router"][p] >= gains["last_barrier"][p] for p in R["PHASES"]),
        "wider deadline made the projection slower",
    )
    return {k: R["clocks"](obs, v) for k, v in gains.items()} | dict(exposed_service_ns=exposed)


def assess(data):
    spans, chosen = T["workload"]()
    words = data["plan"]["ranks"]
    grouped = regroup(spans["P97"], chosen, words)
    need(
        grouped == regroup(spans["P106"], chosen, words)
        and data["physical"]["elf"] == ELF
        and data["physical"]["protocol"] == METHOD,
        "matched cohort and binary",
    )
    groups, _, unique, proof = G["verify_reads"](data, grouped)
    arms = []
    checks = {"layer": [], "early": []}
    for a, rows in enumerate(proof["arms"], 1):
        early = a in (2, 3)
        times = {i: wall for i, _, _, wall in rows}
        estimates = {
            t: (G["phase_overlap"](obs, times) if early else layer_prices(obs, times))
            for t, obs in spans.items()
        }
        key, cut = ("early", "perfect_overlap") if early else ("layer", "next_router")
        for obs in estimates.values():
            checks[key].append(R["passes"](obs[cut]))
        arms.append(dict(arm=a, role=key, service_ns=sum(times.values()), clocks=estimates))

    def verdict(values):
        return (
            "GO_FIXTURE_ONLY"
            if all(values)
            else "INCONCLUSIVE"
            if any(values)
            else "NO_GO_MEASURED_PRICES"
        )

    return dict(
        method=METHOD,
        elf=ELF,
        evidence="MEASURED_READS_TRACE_DERIVED_CLIENT",
        arms=arms,
        layer=verdict(checks["layer"]),
        early=verdict(checks["early"]),
        unique=unique,
        rank_rows=7012,
        router_sites=len(words),
        with_compulsory_reads=len(groups),
        max_advance_to_first_remap_ns=data["plan"]["advance"],
        m3="PARTIAL",
        m4="NOT_MET",
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "grade":
        del sys.argv[1]
        return G["main"](assess, ("ranks", "advance"))
    if len(sys.argv) > 1 and sys.argv[1] == "physical":
        del sys.argv[1]
        return T["LEGACY"]["main"](
            lambda a, r: T["physical"](a, r, method=METHOD, protocol_file=PROTOCOL)
        )
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="mode", required=True)
    for name, fields in (("plan", ("archive", "manifest")), ("attest", ("previous",))):
        p = modes.add_parser(name)
        for k in (*fields, "new-output-dir"):
            p.add_argument("--" + k, type=Path, required=True)
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        commit, tree = T["M"]["B"]["version"]()
        need(sha(PROTOCOL) == METHOD, "layer protocol")
        if a.mode == "plan":
            spans, chosen = T["workload"]()
            words, advance = capture(a.archive, spans)
            grouped = regroup(spans["P97"], chosen, words)
            need(grouped == regroup(spans["P106"], chosen, words), "different layer schedules")
            result = T["plan"](a, grouped) | dict(ranks=words, advance=advance)
        else:
            old = T["verified"](a.previous / "receipt.json", PRIOR_BUILD)
            src = a.previous / "reader"
            dst = a.new_output_dir / "reader"
            need(
                sha(src) == old["binary"] == ELF
                and all(sha(p) == h for p, h in old["libraries"].items()),
                "enrolled executable or provider",
            )
            shutil.copy2(src, dst)
            need(sha(dst) == ELF, "copied binary")
            result = dict(binary=ELF, libraries=old["libraries"], previous=PRIOR_BUILD)
        T["save"](
            a.new_output_dir / "receipt.json",
            result
            | dict(
                status="PASS",
                commit=commit,
                tree=tree,
                protocol=METHOD,
                program=sha(Path(__file__)),
            ),
        )
    except Exception as exc:
        T["save"](a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
