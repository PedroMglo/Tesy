"""Classify the next FIFO demand at observed C317 accepts, using separate clocks."""

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

from audit import audit, primary, require, source, staging


def blocked_with_head(decode, depths, stage_depth, attached):
    queue = deque()
    candidates = {}
    expected_next = None
    for i, event in enumerate(decode, 1):
        if event.kind == 4:
            queue.append(event.work)
        elif event.kind == 5:
            require(queue and queue.popleft() == event.work, "FIFO acceptance mismatch")
            if expected_next is not None:
                require(event.work == expected_next, "next FIFO head changed")
            expected_next = queue[0] if queue else None
            attach, waits = attached.get(event.work, (None, False))
            if waits and expected_next and depths[i] + stage_depth[attach - 1] == 4:
                require(attach not in candidates, "repeated staging attach")
                candidates[attach] = expected_next
    require(not queue and expected_next is None, "unfinished FIFO head")
    return candidates


def head_outcomes(journal, candidates, attached):
    states = {}
    outcomes = defaultdict(Counter)
    labels = {1: "QUEUED", 2: "READING", 3: "READY", 5: "EXPIRED", 7: "CONSUMING"}
    for j, event in enumerate(journal, 1):
        ticket = event["scope"], event["ticket"]
        key = event["call"], event["layer"], event["expert"]
        if j in candidates:
            require(event["kind"] == 6, "observation outside a demand attach")
            head = candidates[j]
            entries = [state for routed, state in states.values()
                       if routed == head[:3] and state != "EXPIRED"]
            require(len(entries) <= 1, "multiple live matches")
            state = entries[0] if entries else "ABSENT"
            eventual = "DIRECT"
            if head in attached:
                eventual = "READING" if attached[head][1] else "READY"
            require((state in {"ABSENT", "QUEUED"} and eventual == "DIRECT")
                    or (state == "READY" and eventual == "READY")
                    or (state == "READING" and eventual in {"READY", "READING"}),
                    "FIFO head later used an incompatible source")
            outcomes[state][eventual] += 1
        kind = event["kind"]
        if kind in (4, 8):
            del states[ticket]
        elif kind in labels:
            if kind == 3 and states[ticket][1] == "EXPIRED":
                continue  # the next retirement under the same lock drops this ticket
            states[ticket] = key, labels[kind]
    require(not states and len(candidates) == sum(sum(cs.values()) for cs in outcomes.values()),
            "terminal conservation")
    direct = sum(sum(outcomes[s].values()) for s in ("ABSENT", "QUEUED") if s in outcomes)
    return {
        "full_with_pending": len(candidates),
        "next_direct_read_eligible": direct,
        "next_ready_copy_eligible": sum(outcomes.get("READY", {}).values()),
        "next_attaches_to_reading_producer": sum(outcomes.get("READING", {}).values()),
        "at_accept_then_at_observed_dispatch": dict(outcomes),
    }


def classify(text, staged):
    # The shared lock auditor validates joins, lifecycle, capacity, byte service,
    # termination and the unique stage prefix at each accept, for this exact raw.
    control = audit(text, staged)
    require(control["ambiguous_occupancy_at_accepts"] == 0, "locked projection required")
    decode, _, _, _, depths, _, _ = primary(text)
    tickets, stage_depth, _, _ = staging(staged)
    attached = {}
    for seq in tickets.values():
        by_kind = {e["kind"]: (i, e) for i, e in seq}
        if 6 in by_kind:
            attach, _ = by_kind[6]
            _, claim = by_kind[7]
            work = tuple(claim[key] for key in ("call", "layer", "expert", "slot", "generation"))
            attached[work] = attach, attach < by_kind[3][0]
    candidates = blocked_with_head(decode, depths, stage_depth, attached)
    row = head_outcomes(staged["journal"], candidates, attached)
    require(row["full_with_pending"] == control["other_work_at_blocked_accept"][
        "necessarily_four_busy"], "eligibility denominator changed")
    return row


def run(raw_dir, output_dir):
    output_dir.mkdir()
    manifest = source.required_files()
    missing = {name: spec for name, spec in manifest.items() if not (raw_dir / name).is_file()}
    result = {"schema": "tesy-c317-at-accept-fifo-head-v1", "evidence": "TRACE_DERIVED",
              "inputs": manifest, "missing": missing, "arms": {},
              "counterfactual_gain": "INCONCLUSIVE"}
    try:
        if missing:
            result["status"] = "NOT_RUN_RAW_REQUIRED"
            return 2
        raw = {name: source.checked_bytes(raw_dir / name, spec) for name, spec in manifest.items()}
        for name, payload in raw.items():
            if name.endswith("/events.tsv"):
                arm = name.removesuffix("/events.tsv")
                staged = json.loads(raw[f"{arm}/staging.json"])
                result["arms"][arm] = classify(payload.decode(), staged)
        require(len(result["arms"]) == 4, "incomplete trace arm inventory")
        result["status"] = "PASS_FIFO_HEAD_CLASSIFICATION"
    except (ValueError, KeyError, OSError) as exc:
        result["status"] = "FAIL"
        result["failure"] = str(exc)
        return 1
    finally:
        temporary = output_dir / "head.json.part"
        with temporary.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write("\n")
        temporary.rename(output_dir / "head.json")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.raw_dir, args.new_output_dir))
