"""Screen one prefix-only hotness ranking with free placement and offline decode replacement."""

import argparse
import hashlib
import json
import signal
from pathlib import Path

from cache_bound import (
    CAMPAIGN,
    EXPERT_BYTES,
    LINK_BPS,
    MANIFEST,
    MANIFEST_SHA,
    MAX_LOADS,
    STEPS,
    minimum,
    read_arm,
)
from cache_boundary import NAMES, boundary, slots

POLICY_PROTOCOL_SHA = "253d99be50b32392889879b11d350ddbf2650d1a0de268d984cbb2e0d5fc773a"


def top40(hotness):
    """This function receives only prefix scores. Its return order includes the fixed tie break."""
    if len(hotness) != 128 or any(type(v) is not int or not 0 <= v <= 2**32 - 1 for v in hotness):
        raise ValueError("invalid C294 route-hotness vector")
    return sorted(range(128), key=lambda expert: (-hotness[expert], expert))[:40]


def report_arm(raw, name, manifest):
    folder = name + ".native"
    entry = manifest[f"results/{CAMPAIGN}/raw/{folder}/initial.json"]
    data = (raw / folder / "initial.json").read_bytes()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("prefix snapshot identity mismatch")
    prefix = json.loads(data)
    physical = slots(prefix)
    selections, coverage = [], []
    outside_prefix = outside_seen = 0
    for layer, obj in enumerate(sorted(prefix["layers"], key=lambda item: item["layer"])):
        heat = obj["route_hotness"]
        selected = top40(heat)
        selections.append(set(selected))
        seen = obj["seen"]
        if len(seen) != 128 or any(v not in (0, 1) for v in seen):
            raise ValueError("invalid historical seen set")
        resident = {e for e, _, s, _ in physical[layer] if s == 2}
        outside_prefix += len(set(selected) - resident)
        outside_seen += sum(not seen[e] for e in selected)
        cutoff = heat[selected[-1]]
        coverage.append(
            {
                "layer": layer,
                "positive": sum(value > 0 for value in heat),
                "seen": sum(seen),
                "selected_zero": sum(heat[e] == 0 for e in selected),
                "cutoff": cutoff,
                "tied_at_cutoff": heat.count(cutoff),
                "selected_at_cutoff": sum(heat[e] == cutoff for e in selected),
            }
        )
    # Open later evidence only after the input-only policy has selected every layer's experts.
    observed_boundary = boundary(raw, name)
    outside_boundary = sum(
        len(ids - original) for ids, original in zip(selections, observed_boundary, strict=True)
    )
    trace = manifest[f"results/{CAMPAIGN}/raw/{folder}/events.tsv"]
    groups, measured = read_arm(raw / folder / "events.tsv", trace)
    floors = [
        minimum(groups[layer::36], 40, initial={layer * 128 + e for e in selected})
        for layer, selected in enumerate(selections)
    ]
    loads = sum(floors)
    return {
        "initial_sha256": entry["sha256"],
        "events_sha256": trace["sha256"],
        "selection_sha256": hashlib.sha256(
            json.dumps([sorted(s) for s in selections], separators=(",", ":")).encode()
        ).hexdigest(),
        "layers_with_positive_scores": sum(row["positive"] > 0 for row in coverage),
        "positive_expert_layer_pairs": sum(row["positive"] for row in coverage),
        "seen_expert_layer_pairs": sum(row["seen"] for row in coverage),
        "selected_zero_score": sum(row["selected_zero"] for row in coverage),
        "selected_owing_to_partial_cutoff_tie": sum(
            row["selected_at_cutoff"]
            for row in coverage
            if row["tied_at_cutoff"] > row["selected_at_cutoff"]
        ),
        "selected_absent_prefix_slots": outside_prefix,
        "selected_never_reserved_by_prefix": outside_seen,
        "selected_absent_observed_decode_entry": outside_boundary,
        "all_zero_layers": [row["layer"] for row in coverage if row["positive"] == 0],
        "coverage_nonzero_layers": [row for row in coverage if row["positive"] > 0],
        "observed_r0_decode_publications": measured,
        "offline_loads_with_free_policy_placement": loads,
        "encoded_bytes": loads * EXPERT_BYTES,
        "dedicated_10gbit_s_tok_s_upper": STEPS * LINK_BPS / (8 * EXPERT_BYTES * loads)
        if loads
        else None,
        "decision": "NO_GO_POLICY" if loads > MAX_LOADS else "GO_COST_SCREEN_ONLY",
    }


def audit(raw):
    data = MANIFEST.read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA:
        raise ValueError("C294 manifest changed")
    frozen = Path(__file__).with_name("causal_prefix_protocol.md")
    if hashlib.sha256(frozen.read_bytes()).hexdigest() != POLICY_PROTOCOL_SHA:
        raise ValueError("ranking protocol changed")
    manifest = {entry["path"]: entry for entry in json.loads(data)["files"]}
    return {
        "schema": "tesy-prefix-hotness-screen-v1",
        "status": "TRACE_DERIVED",
        "policy_protocol_sha256": POLICY_PROTOCOL_SHA,
        "raw_manifest_sha256": MANIFEST_SHA,
        "charged_initial_loads_in_floor": 0,
        "cap_per_layer": 40,
        "decode_tokens": STEPS,
        "max_loads_at_six": MAX_LOADS,
        "expert_bytes": EXPERT_BYTES,
        "dedicated_link_bps": LINK_BPS,
        "arms": {name: report_arm(raw, name, manifest) for name in NAMES},
    }


def deadline(_signal, _frame):
    raise TimeoutError("prefix hotness screen exceeded budget")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    args = ap.parse_args()
    out = args.new_output_dir
    if out.resolve().is_relative_to(args.raw_dir.resolve()):
        ap.error("new output must be outside the historical evidence")
    out.mkdir()
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        report = audit(args.raw_dir)
    except FileNotFoundError:
        report = {"status": "NOT_RUN_RAW_REQUIRED"}
    except (ValueError, KeyError, OSError) as exc:
        report = {"status": "FAIL", "exception_type": type(exc).__name__}
    finally:
        signal.alarm(0)
    pending = out / ".pending"
    with pending.open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    pending.replace(out / "receipt.json")
    print(report["status"])
    return int(report["status"] != "TRACE_DERIVED")


if __name__ == "__main__":
    raise SystemExit(main())
