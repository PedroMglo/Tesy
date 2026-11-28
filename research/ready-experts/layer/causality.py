"""Lower bounds with graph work movable across either side of each layer boundary."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import groupby, pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
E = run_path(HERE.parent / "existence.py")
R, B, SRC, need = (E[k] for k in ("R", "BASE", "SRC", "require"))
METHOD = "bd5a38d4226a85aa3169e2119a087fc4f3096a6deb68a6b40145993a0bdbcc97"
PARENT = "babccc24a5f1e767e738d9fcca36088e5e49cff14267c58a31b09a9ec0fbf5b6"


@dataclass
class Region:
    site: tuple
    internal: int
    jobs: list = field(default_factory=list)


def affine(jobs, bank):
    """A global affine minorant of four-lane service, tight at the specified bank."""
    if not jobs:
        return 0, Counter()
    prices = [job.set_ns + (0 if job.expert in bank else job.read_ns) for job in jobs]
    longest = max(range(len(jobs)), key=lambda i: (prices[i], jobs[i].expert))
    if 4 * prices[longest] >= sum(prices):
        job = jobs[longest]
        return 4 * (job.set_ns + job.read_ns), Counter({job.expert: 4 * job.read_ns})
    eligible = Counter()
    for job in jobs:
        eligible[job.expert] += job.read_ns
    return sum(job.set_ns + job.read_ns for job in jobs), eligible


def cuts(inside, edges, service):
    """Return the maximum valid cut and its service groups, in quarter-nanoseconds."""
    n = len(inside)
    need(n and len(service) == n and len(edges) == n + 1, "cut extent")
    previous = [inside[0] + edges[0], service[0]]
    parents = []
    for i in range(1, n):
        # A boundary earns graph time only if both neighbours take graph time.
        choices = ((previous[0] + edges[i], previous[1]), tuple(previous))
        preds = [int(pair[1] > pair[0]) for pair in choices]
        parents.append(preds)
        previous = [inside[i] + choices[0][preds[0]], service[i] + choices[1][preds[1]]]
    previous[0] += edges[-1]
    state = int(previous[1] > previous[0])
    value = previous[state]
    path = [state]
    for preds in reversed(parents):
        state = preds[state]
        path.append(state)
    return value, path[::-1]


def partition(calls, waves, jobs):
    by_call = defaultdict(list)
    for w in waves:
        by_call[w.site[0]].append(w)
    for c in calls:
        number = c["number"]
        last = c["enter_ns"]
        inside = 0
        regions, edges, seen = [], [], set()
        for site, it in groupby(by_call[number], key=lambda w: w.site[:3]):
            ws = list(it)
            need(site not in seen and last <= ws[0].start, "noncontiguous tile/layer")
            seen.add(site)
            edges.append(ws[0].start - last)
            local = sum(b.start - a.end for a, b in pairwise(ws))
            need(local >= 0, "wave order")
            regions.append(Region(site, local, jobs[number].get(site[1:], [])))
            inside += sum(w.end - w.start for w in ws)
            last = ws[-1].end
        edges.append(c["return_ns"] - last)
        need(
            min(edges) >= 0
            and regions
            and sum(edges) + sum(g.internal for g in regions) + inside
            == c["return_ns"] - c["enter_ns"],
            "call wall conservation",
        )
        yield number, regions, edges


def load_arm(archive, label, prior):
    (calls, _, _), auth = B["read_arm"](archive, label, prior)
    name, family, _ = SRC["SOURCES"][label]
    root = archive / ("part-" + label[1:]) / name
    offered = set()
    if label == "P106":
        seal, rows, tiers, _ = SRC["Q"]["read_new"](root, family)
        offered = set(map(tuple, seal["offered_keys"]))
    else:
        rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        rec = json.loads((root / "ON/receipt.json").read_bytes())
        log = root / "ON/raw" / rec["native_ids"]["raw_stderr_file"]
        tiers, _ = SRC["T"]["mapping"](log.read_bytes(), rows)
    jobs, _, _ = R["raw_groups"](rows, tiers)
    host = SRC["NATIVE"]["host_trace"](rows)
    waves, _ = SRC["timeline"](rows)
    regions = list(partition(host["calls"], waves, jobs))
    need(sum(len(g.jobs) for _, gs, _ in regions for g in gs) == 1918, "charged population")
    return regions, auth, offered, E["supporting_credit"](calls, jobs)["first_final"]


def evaluate(regions, bank, offered, exterior):
    phases = defaultdict(Counter)
    bounds = Counter()
    credits = defaultdict(Counter)
    peak = (0, (), 0)
    for number, groups, edges in regions:
        lines = [affine(g.jobs, bank) for g in groups]
        services = [a - sum(v for k, v in h.items() if k in bank) for a, h in lines]
        interior = [4 * g.internal for g in groups]
        boundaries = [4 * e for e in edges]
        value, selected = cuts(interior, boundaries, services)
        global4 = max(sum(interior) + sum(boundaries), sum(services))
        need(value >= global4, "region cut cannot weaken either global cut")
        entry = phases[B["phase"](number)]
        entry.update(
            calls=1, groups=len(groups), local_ns=(value + 3) // 4, global_ns=(global4 + 3) // 4
        )
        if number <= 46:
            for g, cost in zip(groups, services, strict=True):
                if cost > peak[0]:
                    peak = (cost, g.site, len(g.jobs))
        # The chosen cut and branches remain valid even after replacing the selector.
        scores = Counter()
        for used, (_, coeff) in zip(selected, lines, strict=True):
            if used:
                scores.update(coeff)
        constant = value + sum(v for key, v in scores.items() if key in bank)
        for clock, relevant in (("first_final", number <= 46), ("decode", number >= 3)):
            if relevant:
                bounds[clock] += constant
                credits[clock].update(scores)
    result = {}
    for clock, include in (
        ("first_final", ("prefill", "decode_before_final")),
        ("decode", ("decode_before_final", "decode_tail")),
    ):
        result[clock] = {
            key: exterior[clock] + sum(phases[p][key] for p in include)
            for key in ("global_ns", "local_ns")
        }
        largest = sorted((credits[clock][k] for k in offered), reverse=True)[: R["BUDGET"]]
        universal = exterior[clock] + (bounds[clock] - sum(largest) + 3) // 4
        result[clock]["all_banks_certificate_ns"] = universal
        need(universal <= result[clock]["local_ns"], "certificate excludes its own witness")
    return {
        "clocks": result,
        "phases": dict(phases),
        "peak_before_final": {
            "site_call_tile_layer": peak[1],
            "jobs": peak[2],
            "service_quarter_ns": peak[0],
        },
    }


def run(archive):
    need(SRC["digest"](HERE / "protocol.md") == METHOD, "protocol identity")
    parent = SRC["pinned"](HERE.parent / "existence-result.json", PARENT)
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    data = {k: load_arm(archive, k, prior[k]) for k in ("P106", "P97")}
    offered = data["P106"][2]
    bank = set(sorted(offered, key=lambda k: (-data["P106"][3][k], -data["P97"][3][k], k))[:353])
    digest = hashlib.sha256(json.dumps(sorted(bank), separators=(",", ":")).encode()).hexdigest()
    need(digest == parent["witness_keys_sha256"] and len(offered) == 2829, "original selector")
    arms = {}
    for k, (regs, auth, _, _) in data.items():
        arm = evaluate(regs, bank, offered, auth["outside_calls_ns"])
        empty = evaluate(regs, set(), offered, auth["outside_calls_ns"])
        for clock, row in arm["clocks"].items():
            need(row["global_ns"] == parent["arms"][k]["witness"][clock], "parent clock")
            row["all_banks_certificate_ns"] = max(
                row["all_banks_certificate_ns"], empty["clocks"][clock]["all_banks_certificate_ns"]
            )
            need(row["all_banks_certificate_ns"] <= row["local_ns"], "invalid universal bound")
        arms[k] = arm

    def misses(key):
        return any(
            B["joint"]({c: row[key] for c, row in arm["clocks"].items()}) < 0
            for arm in arms.values()
        )

    return {
        "status": "TRACE_DERIVED",
        "schema": "tesy.layer_causality.v1",
        "decision": "NO_GO_ALL_FIXED_BANKS"
        if misses("all_banks_certificate_ns")
        else "NO_GO_WITNESS"
        if misses("local_ns")
        else "HEADROOM_ONLY",
        "protocol_sha256": METHOD,
        "script_sha256": SRC["digest"](Path(__file__)),
        "parent_sha256": PARENT,
        "bank_sha256": digest,
        "arms": arms,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve()
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing": missing.name,
        }
    except (ValueError, KeyError, OSError, AssertionError) as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    pending = a.new_output_dir / ".pending"
    pending.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    pending.rename(a.new_output_dir / "receipt.json")
    print(result["status"], result.get("decision", result.get("reason", "")))
    raise SystemExit(result["status"] != "TRACE_DERIVED")
