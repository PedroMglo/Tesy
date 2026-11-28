"""Price real mandatory NVMe reads on both original customer clocks."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
T = run_path(HERE / "transport.py")
R = run_path(HERE / "replay.py")
need, sha, size = T["need"], T["sha"], T["SIZE"]
PHASES = R["PHASES"]
LINK = (16_000_000_000 * 4 * 128 + 8 * 130 - 1) // (8 * 130)


def read(path):
    return json.loads(path.read_bytes())


def compress(obj):
    return gzip.compress(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(), mtime=0)


def saved(obs, durations):
    gain = Counter(dict.fromkeys(PHASES, 0))
    for i, (site, start, enter, leave, end, _, _) in enumerate(obs["waves"]):
        floor = (end - leave) + max(enter - start, durations.get(i, 0))
        gain[R["phase"](site[0])] += end - start - floor
    return R["clocks"](obs, gain)


def bandwidth(obs, groups):
    def at(rate):
        return saved(obs, {i: (n * size * 10**9 + rate - 1) // rate for i, n in groups.items()})

    # A small rate can put the first callback on the wrong side of the later
    # client cut only if the provided spans are inconsistent. Both include it.
    lo, hi = 1, 10**12
    need(not R["passes"](at(lo)) and R["passes"](at(hi)), "unbracketed bandwidth")
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if R["passes"](at(mid)):
            hi = mid
        else:
            lo = mid
    return dict(min_B_per_s=hi, at_min=at(hi), at_first_insufficient=at(lo), at_link=at(LINK))


def phase_overlap(obs, wall):
    intervals = {p: [] for p in PHASES}
    waits = Counter()
    for i, (start, stop) in enumerate(obs["calls"], 1):
        intervals[R["phase"](i)].append((start, stop))
    for site, _, enter, leave, _, _, _ in obs["waves"]:
        waits[R["phase"](site[0])] += leave - enter
    best, serial, outside = {}, {}, {}
    for i, p in enumerate(PHASES):
        span = intervals[p][-1][1] - intervals[p][0][0]
        rest = span - waits[p]
        best[p] = span - max(rest, wall[i])
        serial[p] = span - rest - wall[i]
        outside[p] = rest
    ideal = R["clocks"](obs, best)
    unhidden = R["clocks"](obs, serial)
    return dict(
        perfect_overlap=ideal,
        serial=unhidden,
        host_outside_wait_ns=outside,
        overlap_needed_ns={k: max(0, -unhidden[k + "_margin"]) for k in ("first", "decode")},
    )


def verify_reads(data, chosen):
    groups = Counter(i for _, i, _, _, _ in chosen)
    phases = Counter(p for p, _, _, _, _ in chosen)
    spec = data["plan"]
    unique = len({(layer, expert) for _, _, _, layer, expert in chosen})
    need(
        spec["counts"] == [list(r) for r in sorted(groups.items())]
        and spec["phases"] == [list(r) for r in sorted(phases.items())]
        and spec["unique"] == unique,
        "original demand and phase cuts",
    )
    proof = T["parse"](data["stdout"].splitlines(), spec)
    facts = data["physical"]
    need(
        facts["status"] == "MEASURED"
        and facts["requested_B"] == (4 * 1519 + unique) * size
        and facts["disk_delta"]["read_sectors_512B"] * 512 >= facts["requested_B"]
        and facts["cgroup"]["swap_current"] == 0
        and facts["max_sample_gap_s"] < 3
        and facts["full_model_requests"] == 0
        and facts["pcie"]["current_link_width"] == "4"
        and facts["pcie"]["current_link_speed"] == "16.0 GT/s PCIe",
        "device, scope or byte receipt",
    )
    return groups, phases, unique, proof


def evaluate(data):
    spans, chosen = T["workload"]()
    groups, phases, unique, proof = verify_reads(data, chosen)
    arms = []
    for a, rows in enumerate(proof["arms"], 1):
        early = a in (2, 3)
        interval = {i: wall for i, _, _, wall in rows}
        totals = dict(
            records=sum(n for _, n, _, _ in rows),
            groups=len(rows),
            pread_join_ns=sum(rd for _, _, rd, _ in rows),
            service_ns=sum(interval.values()),
        )
        estimates = {
            t: (phase_overlap(obs, interval) if early else saved(obs, interval))
            for t, obs in spans.items()
        }
        arms.append(dict(arm=a, role="EARLY" if early else "CALLBACK", **totals, clocks=estimates))
    good_a = [R["passes"](o) for a in (arms[0], arms[3]) for o in a["clocks"].values()]
    good_b = [
        R["passes"](o["perfect_overlap"]) for a in (arms[1], arms[2]) for o in a["clocks"].values()
    ]

    def verdict(signs):
        return (
            "GO_FIXTURE_ONLY"
            if all(signs)
            else "INCONCLUSIVE"
            if any(signs)
            else "NO_GO_MEASURED_PRICES"
        )

    return dict(
        method=T["METHOD"],
        schema="tesy.compulsory_transport.v1",
        unit="ns",
        service="MEASURED_NVME",
        projected_client="TRACE_DERIVED_CONDITIONAL",
        arms=arms,
        bandwidth={t: bandwidth(obs, groups) for t, obs in spans.items()},
        pcie_B_per_s=LINK,
        phase_records={p: phases[i] for i, p in enumerate(PHASES)},
        unique=unique,
        parity_ns=proof["parity_ns"],
        component_sha256_count=proof["component_hashes"],
        timed_markers=proof["timed_markers"],
        callback=verdict(good_a),
        early=verdict(good_b),
        m3="PARTIAL",
        m4="NOT_MET",
    )


def main(assess=evaluate, extra_fields=()):
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path)
    mode.add_argument("--new-output-dir", type=Path)
    cli.add_argument("--physical", type=Path)
    cli.add_argument("--plan", type=Path)
    a = cli.parse_args()
    if a.new_output_dir:
        if not (a.physical and a.plan):
            cli.error("physical and plan receipts required")
        a.new_output_dir.mkdir()
    try:
        if a.new_output_dir:
            receipt = read(a.physical / "receipt.json")
            need(
                receipt["status"] == "MEASURED"
                and sha(a.physical / "stdout") == receipt["stdout_sha256"]
                and sha(a.physical / "samples.jsonl") == receipt["samples_sha256"]
                and sha(a.plan / "receipt.json") == receipt["plan_sha256"],
                "physical chain",
            )
            plan = read(a.plan / "receipt.json")
            data = dict(
                physical={k: v for k, v in receipt.items() if k != "timing"},
                stdout=(a.physical / "stdout").read_text(),
                plan={
                    k: plan[k]
                    for k in ("pack_stat", "counts", "phases", "unique", "windows", *extra_fields)
                },
                physical_sha256=sha(a.physical / "receipt.json"),
            )
            need(
                T["parse"](data["stdout"].splitlines(), data["plan"]) == receipt["timing"],
                "closed output",
            )
        else:
            data = json.loads(gzip.decompress((a.check / "reads.json.gz").read_bytes()))
        result = assess(data)
        if a.new_output_dir:
            with (a.new_output_dir / "reads.json.gz").open("xb") as f:
                f.write(compress(data))
            T["save"](a.new_output_dir / ".pending", result)
            (a.new_output_dir / ".pending").rename(a.new_output_dir / "decision.json")
        else:
            need(result == read(a.check / "decision.json"), "different public result")
        print(result.get("callback", result.get("layer")), result["early"])
    except Exception as exc:
        if a.new_output_dir:
            T["save"](
                a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc))
            )
        raise


if __name__ == "__main__":
    main()
