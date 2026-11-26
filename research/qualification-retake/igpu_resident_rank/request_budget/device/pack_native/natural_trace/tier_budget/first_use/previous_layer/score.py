"""Price strict routed jobs with a perfect one-layer predictor in the observed packed T2."""

import argparse
import hashlib
import json
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import accumulate
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FIRST = run_path(str(HERE.parent / "score.py"))
check, NS, SIZE = (FIRST[k] for k in ("check", "NS", "PAYLOAD"))
origin = FIRST["RELEASE"]["origin"]
RATES = (4_500_000_000, 8_000_000_000)
PARENT = "cbbba4262589e1c55aa1f57393f207384dc42c3ddea7a2bd5c299ef5d79fa01e"
PROTOCOL = "66487988c1a0a636077ab69317fd672c86559b37825ba8869b5687300959120f"


@dataclass(frozen=True)
class Cut:
    site: tuple
    ns: int
    drained: bool
    epoch: int
    index: int


def trace_cuts(rows):
    """Count audited queue, claim and slot transitions at callback boundaries."""
    loading = claimed = queued = epoch = 0
    opened = None
    cells = defaultdict(list)
    services = sorted((r.begin, r.ns) for r in rows if r.kind in (16, 30))
    check(all(0 < a <= b for a, b in services), "invalid worker service interval")
    n = 0
    for r in rows:
        k = r.kind
        if k == 1 and r.call == 3:
            break
        if k == 5 and r.a == 1:
            loading += 1
            claimed += r.b
        elif k == 6 and r.b == 1:
            queued += 1
        elif k == 11:
            loading += 1
        elif k == 12:
            queued += 1
        elif k in (13, 14, 28):
            queued -= 1
            claimed += int(k == 13)
        elif k == 17:
            claimed -= 1
            loading -= 1
        elif k == 18:
            raise ValueError("failed service in qualified prefill")
        if k in (11, 12, 13, 14, 16, 17, 28, 30):
            epoch += 1
            check(min(loading, claimed, queued) >= 0, "negative manager occupancy")
        if k == 9:
            check(opened is None, "nested callback")
            opened = Cut(origin(r), r.ns, not (loading or claimed or queued), epoch, n)
        if k == 23:
            check(opened and opened.site == origin(r) and r.ns >= opened.ns, "unpaired callback")
            end = Cut(origin(r), r.ns, not (loading or claimed or queued), epoch, n)
            cells[opened.site[:3]].append((opened, end))
            n += 1
            opened = None
    check(opened is None, "incomplete prefill")
    return cells, ([a for a, _ in services], list(accumulate((b for _, b in services), max)))


def horizon(cells, index, site):
    """Grant free early service if no ordered predecessor is proved."""
    c, t, layer, _ = site
    waves = cells[c, t, layer]
    start = waves[0][0]
    if start.site != site or site[-1] not in (0, -1):
        return "earlier_wave_unbounded", None
    if layer == 0:
        return "layer0", 0
    prev = cells.get((c, t, layer - 1))
    if not prev:
        return "missing_predecessor_unbounded", None
    last = prev[-1][1]
    if last.ns > start.ns:
        return "unordered_predecessor_unbounded", None
    gap = start.ns - last.ns
    if last.index + 1 != start.index or any(
        w[-1][1].index - w[0][0].index + 1 != len(w) for w in (prev, waves)
    ):
        return "noncontiguous", gap
    starts, ends = index
    j = bisect_left(starts, start.ns)
    crossing = gap and j and ends[j - 1] > last.ns
    if crossing or not (last.drained and start.drained) or start.epoch != last.epoch:
        return "occupied", gap
    return "drained", gap


def price(reads, gap):
    """Integer bytes/whole jobs and a continuous-time relaxation at the same aggregate rate."""
    n = len(reads)
    total = n * SIZE
    row = {"jobs": n}
    for rate, label in zip(RATES, ("4p5", "8"), strict=True):
        demand = total * NS
        # None grants complete early service to an unidentifiable group.
        allowance = demand if gap is None else min(demand, gap * rate)
        whole = allowance // (NS * SIZE)
        row.update(
            {
                "partial_bytes_" + label: allowance // NS,
                "whole_jobs_" + label: whole,
                "partial_residual_ns_" + label: (demand - allowance) // rate,
                "whole_residual_ns_" + label: (n - whole) * SIZE * NS // rate,
            }
        )
    floor = FIRST["RELEASE"]["four_lanes"](reads)
    for divisor, label in ((1, "1x"), (2, "half")):
        read_floor = floor // divisor
        row["read_residual_ns_" + label] = 0 if gap is None else max(0, read_floor - gap)
    return row


def summarize(cells):
    total = Counter()
    for row in cells:
        total.update(row)
    return dict(total)


def assess(args):
    sha = FIRST["TIER"]["sha"]
    check(sha(HERE / "protocol.md") == PROTOCOL, "protocol")
    baseline = FIRST["checked"](HERE.parent / "result.json", PARENT)
    check(
        FIRST["assess"](args) == baseline, "full DATA authority, target route and first-use price"
    )
    rows, h = FIRST["TIER"]["PFJ"]["read_journal"](args.family / "ON/raw/events.pfj")
    check(h["journal_sha256"] == baseline["input_sha256"]["ON/raw/events.pfj"], "journal")
    host = FIRST["TIER"]["NATIVE"]["host_trace"](rows)
    cpu = FIRST["checked"](HERE.parents[1] / "evidence/packed.json", FIRST["TIER_SHA"])
    groups = FIRST["strict_sites"](rows, host)
    cuts, index = trace_cuts(rows)
    begin_end = sorted(
        (a.index, a.site[0], a.ns, b.ns) for pairs in cuts.values() for a, b in pairs
    )
    check(
        [v[1:] for v in begin_end] == [v for v in host["callback_spans"] if v[0] <= 2],
        "all callback intervals in host order",
    )
    out = []
    evidence = []
    last_end = 0
    for site, jobs in groups.items():
        if site[2] not in cpu["tier_layers"]["CPU"]:
            continue
        condition, gap = horizon(cuts, index, site)
        first_begin = cuts[site[:3]][0][0].ns
        if gap is not None:
            check(first_begin - gap >= last_end, "overlapping target windows")
            last_end = first_begin
        costs = price([j[0] for j in jobs], gap)
        out.append((site[0], costs))
        evidence.append(
            dict(
                call=site[0],
                tile=site[1],
                layer=site[2],
                wave=site[3],
                horizon=condition,
                gap_ns=gap,
                **costs,
            )
        )
    totals = summarize(c for _, c in out)
    by_call = {str(i): summarize(c for call, c in out if call == i) for i in (1, 2)}
    check(
        all(by_call[str(i)]["jobs"] == baseline["by_tier"]["CPU"][str(i)]["jobs"] for i in (1, 2)),
        "same jobs per phase",
    )
    check(totals["jobs"] == 375 and len(out) == 110, "strict CPU scope")
    budget = baseline["CPU_first_final_budget_ns"]
    margins = {k: budget - v for k, v in totals.items() if "residual_ns" in k}
    labels = Counter(r["horizon"] for r in evidence)
    unknown = set(labels) - {"layer0", "drained"}
    decisions = {
        k: "NO_GO_FIXED_SCOPE" if m < 0 else ("INCONCLUSIVE" if unknown else "HEADROOM_ONLY")
        for k, m in margins.items()
    }
    return {
        "status": "TRACE_DERIVED_SECONDARY_PREVIOUS_LAYER",
        "protocol_sha256": PROTOCOL,
        "verifier_sha256": sha(Path(__file__)),
        "first_use_sha256": PARENT,
        "inputs_sha256": baseline["input_sha256"],
        "route": baseline["route"],
        "sampled_ids_sha256": baseline["sampled_ids_sha256"],
        "payload_per_expert": SIZE,
        "budget_ns": budget,
        "windows": dict(labels),
        "usable_or_optimistic_gap_ns": sum(r["gap_ns"] or 0 for r in evidence),
        "by_call": by_call,
        "totals": totals,
        "margin_ns": margins,
        "decision": decisions,
    }, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("family", "backend", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        receipt, evidence = assess(args)
        columns = list(evidence[0])
        lines = ["\t".join(columns)]
        lines.extend("\t".join(str(row[k]) for k in columns) for row in evidence)
        data = ("\n".join(lines) + "\n").encode()
        with (args.new_output_dir / "windows.tsv").open("xb") as f:
            f.write(data)
        receipt["windows_sha256"] = hashlib.sha256(data).hexdigest()
    except Exception as exc:
        receipt = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(receipt["status"], receipt.get("reason", ""))
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
