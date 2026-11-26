"""Stock E20 Aster cost screen with two contexts in a single server lifetime."""

import argparse
import hashlib
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
sys.path.insert(0, str(QUAL))
from aster_budget import probe as budget  # noqa: E402
from aster_cache_geometry.verify import probe_inputs  # noqa: E402
from aster_split.probe import require, save  # noqa: E402
from c2_server_run import json_bytes  # noqa: E402
from two_turn_pair import digest, read  # noqa: E402

PROTOCOL = "a63dca38d351656ce2a7dec618068484605731fc1d78219f9cef18a53f3fa802"
E10 = "b26808e96d641a78d132ba44804957be69b2e66f3adbbe23ab6eb4173c188e2d"
ORDERED = "a45a64ec4a1eaa167157de9939ec6962a2f911e77ff4a7ee08246a8d972d20a4"
FIRST = "2e157cc172aedb5d3ba90db83f9c8505df543fa277b52624117eaee46a44ed80"
SECOND = "acdc1fc68a6fefcd7a30c6a9637b44d3187d1ce97f58d582fcf6fdc5379170ea"


def common_prefix(left, right):
    return next(
        (i for i in range(min(len(left), len(right))) if left[i] != right[i]),
        min(len(left), len(right)),
    )


def projection(rows):
    base = sum(row["server_prompt_s"] + row["client_overhead_s"] for row in rows)
    budget_s = 1800
    cost = {
        name: base + 340 * fn(rows[0]["step_s"]) + 451 * fn(rows[1]["step_s"])
        for name, fn in (("favorable", min), ("mean", statistics.mean), ("unfavorable", max))
    }
    decision = "INCONCLUSIVE_BUDGET"
    if cost["favorable"] > budget_s:
        decision = "NO_GO_STOCK_REFERENCE_BUDGET"
    elif cost["unfavorable"] <= budget_s:
        decision = "GO_CONSIDER_BOUNDED_PAIR"
    return {
        "decision": decision,
        "historical_nonfirst_steps": [340, 451],
        "estimated_fixed_s": base,
        "combined_step_budget_s": budget_s - base,
        "projected_historical_s": cost,
        "margins_s": {k: budget_s - v for k, v in cost.items()},
    }


class Probe:
    run_id = "stock-aster-full-e20-budget"
    ram_profile = "R0_E20"
    pass_status = "PASS_STOCK_ASTER_E20_COST_OBSERVATION_ONLY"
    protocol_path = HERE / "protocol.md"
    timeout_s = 420

    def __init__(self, history, receipt):
        require(
            hashlib.sha256(self.protocol_path.read_bytes()).hexdigest() == PROTOCOL,
            "changed E20 probe protocol",
        )
        r = read(receipt, E10)
        row = r["after_ready"]
        require(
            r["status"] == "PASS_STOCK_ASTER_COST_OBSERVATION_ONLY"
            and r["child_gone"] is True
            and row["tokens"] == row["observed_step_endpoints"] == 8
            and row["observed_token_stream_sha256"] == ORDERED
            and row["input_sha256"] == FIRST,
            "unqualified E10 reference",
        )
        second = probe_inputs(history)[1]
        self.prompts = [second[:121], second]
        require(
            digest(self.prompts[0]) == FIRST and digest(second) == SECOND and len(second) == 435,
            "C133 input identity",
        )
        self.e10_ordered = row["observed_token_stream_sha256"]

    def run(self, pid, raw, cancelled, progress):
        port = budget.listener_port(raw)
        deadline = time.monotonic() + self.timeout_s
        rows = []
        lcps = []
        for turn, (ids, cached) in enumerate(zip(self.prompts, (0, 122), strict=True), 1):
            stem = f"turn-{turn}"
            data, elapsed, request_sha = budget.exchange(
                pid, raw, cancelled, progress, ids, stem, port, deadline
            )
            row, generated, steps = budget.trajectory(data, elapsed, len(ids), cached)
            row |= {
                "input_sha256": digest(ids),
                "request_sha256": request_sha,
                "sse_sha256": hashlib.sha256(data).hexdigest(),
                "evaluated": len(ids),
                "prompt_n": len(ids) - cached,
                "cache_n": cached,
                "step_s": steps,
                "client_overhead_s": max(
                    0.0, elapsed - row["server_prompt_s"] - row["server_generation_s"]
                ),
            }
            if turn == 1 and steps:
                lcps = [common_prefix(ids + generated[:n], self.prompts[1]) for n in (7, 8)]
                row["lcp_after_seven_and_eight"] = lcps
            save(raw / f"{stem}-observation.json", json_bytes(row))
            rows.append(row)
            if not steps:
                return self.report(
                    rows, {"decision": row["decision"], "projected_historical_s": None}
                )
            if turn == 1:
                require(
                    row["observed_token_stream_sha256"] == self.e10_ordered,
                    "T1 ordered IDs differ from E10",
                )
                require(lcps == [122, 122], "T1 state incompatible with T2 prefix")
        return self.report(rows, projection(rows))

    @staticmethod
    def report(rows, decision):
        return {
            "protocol_sha256": PROTOCOL,
            "e10_receipt_sha256": E10,
            "requests": rows,
            **decision,
        }


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--historical-results", type=Path, required=True)
    parser.add_argument(
        "--e10-receipt", type=Path, default=QUAL / "aster_budget/physical-r1/receipt.json"
    )
    sys.path.insert(0, str(QUAL / "aster_full_ready"))
    from loader import cli_for

    if "--help" in sys.argv or "-h" in sys.argv:
        parser.print_help()
        cli_for()
        return
    args, rest = parser.parse_known_args()
    sys.argv[1:] = rest
    cli_for(probe=Probe(args.historical_results, args.e10_receipt))


if __name__ == "__main__":
    main()
