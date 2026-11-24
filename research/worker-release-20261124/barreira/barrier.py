"""Identify the observed last router publication for C317 FIFO heads at saturation."""
import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import primary, require, source, staging  # noqa: E402
from head import blocked_with_head, head_outcomes  # noqa: E402

HEAD_RECEIPT = "0433bed283cec04478b136fced1461ac717d28b41d5fc5422851a7695bd69599"


def describe(values):
    if not values:
        return None
    return {"minimum": min(values), "median": median(values), "maximum": max(values)}


def measure(decode, assignments, heads, anchor_states):
    publishes = defaultdict(list)
    waits = defaultdict(list)
    accepts = {}
    for i, event in enumerate(decode, 1):
        route = event.call, event.layer, event.route
        if event.kind == 5:
            require(event.work not in accepts, "repeated primary acceptance")
            accepts[event.work] = (i, event)
        if event.kind == 10:
            publishes[route].append((i, event))
        if event.kind in (11, 12):
            waits[route].append((i, event))
    groups = defaultdict(list)
    seen = set()
    for anchor, source_state in anchor_states.items():
        if source_state == "READING":
            continue
        blocked, head = assignments[anchor], heads[anchor]
        _, b = accepts[blocked]
        _, h = accepts[head]
        route = h.call, h.layer, h.route
        require(route == (b.call, b.layer, b.route), "different router barriers")
        require(head not in seen, "repeated FIFO generation")
        seen.add(head)
        pubs = publishes[route]
        require(len(pubs) >= 2 and {blocked, head} <= {e.work for _, e in pubs},
                "incomplete competing publications")
        require(len(waits[route]) == 2, "missing route wait")
        (ib, begin), (ie, end) = waits[route]
        require(begin.kind == 11 and end.kind == 12
                and ib < pubs[0][0] and pubs[-1][0] < ie
                and begin.us <= pubs[0][1].us <= pubs[-1][1].us <= end.us,
                "last publication outside the observed router wait")
        last, penultimate = pubs[-1][1], pubs[-2][1]
        queue_gap = h.us - b.us
        tail_gap = last.us - penultimate.us
        require(queue_gap >= 0 and tail_gap >= 0, "inverted primary lock timestamps")
        winner = "other"
        if last.work == head:
            winner = "fifo_head"
        elif last.work == blocked:
            winner = "blocked"
        kind = "ready_copy" if source_state == "READY" else "direct_read"
        groups[kind].append((route, winner, queue_gap, tail_gap))
    counts = {}
    for name, rows in [("any", [r for rs in groups.values() for r in rs]), *sorted(groups.items())]:
        winners = Counter(w for _, w, _, _ in rows)
        counts[name] = {
            "episodes": len(rows),
            "distinct_barriers": len({r for r, _, _, _ in rows}),
            "last_publication": dict(winners),
            "fifo_head_is_last": {
                "accept_to_head_accept_us": describe(
                    [q for _, w, q, _ in rows if w == "fifo_head"]),
                "last_minus_penultimate_publish_us": describe(
                    [s for _, w, _, s in rows if w == "fifo_head"]),
            },
        }
    return counts


def analyse(text, staged, expected):
    decode, _, _, _, pd, _, _ = primary(text)
    tickets, sd, _, _ = staging(staged)
    matched, blocked = {}, {}
    for seq in tickets.values():
        events = {event["kind"]: (j, event) for j, event in seq}
        if 6 in events:
            claim = events[7][1]
            work = tuple(claim[key] for key in ("call", "layer", "expert", "slot", "generation"))
            anchor = events[6][0]
            matched[work] = anchor, anchor < events[3][0]
            blocked[anchor] = work
    heads = blocked_with_head(decode, pd, sd, matched)
    observed = head_outcomes(staged["journal"], heads, matched)
    require(observed == expected, "eligibility receipt no longer matches this arm")
    labels = {}
    for j, work in heads.items():
        result = head_outcomes(staged["journal"], {j: work}, matched)
        (state,) = result["at_accept_then_at_observed_dispatch"]
        labels[j] = state
    row = measure(decode, blocked, heads, labels)
    require(expected["next_direct_read_eligible"] + expected["next_ready_copy_eligible"] ==
            row["any"]["episodes"], "lost an eligible FIFO generation")
    return row


def run(raw, reference, out):
    out.mkdir()
    manifest = source.required_files()
    result = {"schema": "tesy-c317-fifo-observed-last-publication-v1", "evidence": "TRACE_DERIVED",
              "inputs": manifest, "head_receipt_sha256": HEAD_RECEIPT, "arms": {},
              "counterfactual_gain": "INCONCLUSIVE"}
    try:
        ref_bytes = reference.read_bytes()
        require(hashlib.sha256(ref_bytes).hexdigest() == HEAD_RECEIPT, "unexpected head receipt")
        ref = json.loads(ref_bytes)
        require(ref["inputs"] == manifest, "changed raw manifest")
        missing = {n: spec for n, spec in manifest.items() if not (raw / n).is_file()}
        if missing:
            result.update(status="NOT_RUN_RAW_REQUIRED", missing=missing)
            return 2
        inputs = {n: source.checked_bytes(raw / n, spec) for n, spec in manifest.items()}
        for arm, expected in ref["arms"].items():
            row = analyse(inputs[arm + "/events.tsv"].decode(),
                          json.loads(inputs[arm + "/staging.json"]), expected)
            result["arms"][arm] = row
        result["status"] = "PASS_OBSERVED_BARRIER_IDENTIFIED"
    except (OSError, ValueError, KeyError) as exc:
        result.update(status="FAIL", failure=str(exc))
        return 1
    finally:
        temporary = out / "barrier.json.part"
        with temporary.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write("\n")
        temporary.rename(out / "barrier.json")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--head-receipt", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.raw_dir, args.head_receipt, args.new_output_dir))
