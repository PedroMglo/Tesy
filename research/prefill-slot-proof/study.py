"""Check a frozen C135 cache certificate and its conditional time ceilings."""

import argparse
import hashlib
import sys
from pathlib import Path

from critical import summarize
from critical_intervals import interval_report
from output import publish
from select_slots import select
from verify_slots import verify

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/worker-release-20261124"))
from prefill import C261, report, source, trace_rows  # noqa: E402


def study(trace):
    base = report(trace)  # #44 checks the pinned SHA, input schema, calls, tiers and widths.
    _, rows = trace_rows(trace)
    plan = select(rows)
    schedule = plan.pop("schedule")
    selected = plan.pop("load_generations")
    relaxed = plan.pop("optimistic_load_union")
    proof = verify(rows, schedule)
    certified = proof.pop("load_generations")
    if sorted(map(tuple, certified)) != sorted(map(tuple, selected)):
        raise ValueError("selector and verifier disagree on generations")

    scenarios = {}
    for label, removed in [
        ("all_observed_cross_tile", None),
        ("optimistic_fixed_destination_union", relaxed),
        ("verified_schedule", certified),
    ]:
        scenarios[label] = summarize(rows, removed)
        scenarios[label]["four_worker_relaxation"] = interval_report(rows, removed)

    phase = source.archived(C261)["prefill_call_s"]
    return {
        "schema": "tesy-c135-fixed-destination-v1",
        "evidence": "TRACE_DERIVED / conditional on fixed wave geometry and service",
        "c135_sha256": base["c135_trace_sha256"],
        "protocol_sha256": hashlib.sha256(
            Path(__file__).with_name("protocol.md").read_bytes()).hexdigest(),
        "prefill_5_plus_148_s": phase,
        "diagnostic_ten_percent_prefill_us": phase * 100_000,
        "selection": plan,
        "certificate_source_target_evict_seq": schedule,
        "joint_replay": proof,
        "charged_copy_payload_by_tier_B": {
            tier: n * 13_219_200 for tier, n in proof["loads_avoided"].items()},
        "scenarios": scenarios,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    publish(args.new_output_dir, lambda: study(args.trace))


if __name__ == "__main__":
    main()
