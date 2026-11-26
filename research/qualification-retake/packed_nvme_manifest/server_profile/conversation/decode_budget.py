"""Conditional budgets for the first final content in each completed nominal T2."""

import argparse
import hashlib
import json
from pathlib import Path

AUTHORITY = "4cefe36f27fa59f8d3a5c80a74b40ca780ea190df8ca930c4cdbd3c144ea41ac"


def screen(path):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != AUTHORITY:
        raise ValueError("paired natural workload receipt")
    pair = json.loads(data)
    if pair["natural_requests"] != 12 or pair["servers"] != 6:
        raise ValueError("paired workload coverage")
    out = {}
    work = set()
    for order in ("ROP", "POR"):
        out[order] = {}
        for arm in order:
            first, turn = pair[order]["rows"][arm]
            if (
                first["label"],
                turn["label"],
                turn["cache_n"],
                turn["prompt_n"],
                turn["completion_n"],
                turn["predicted_n"],
                turn["functional"],
            ) != ("T1", "T2", 2044, 153, 47, 47, "PASS"):
                raise ValueError("prefill/history/confirmed workload")
            work.add(
                (
                    turn["input_bytes_sha256"],
                    turn["sampled_ids_sha256"],
                    turn["stable_frames_sha256"],
                )
            )
            first_final = turn["first_final_s"]
            decode = turn["decode_s"]
            prefill = turn["prefill_s"]
            allowed = decode - (first_final - 10)
            # Give this counterfactual the entire phase saving, even if some of
            # that saving actually lands after the client's first final content.
            rest = first_final - 10 - (decode - 47 / 6)
            out[order][arm] = dict(
                first_final_s=first_final,
                decode_s=decode,
                prefill_s=prefill,
                floor_if_decode_free_s=first_final - decode,
                max_decode_s_if_only_decode_changes=allowed if allowed >= 0 else None,
                required_tok_s_if_only_decode_changes=47 / allowed if allowed > 0 else None,
                other_reduction_s_at_exactly_six=rest,
                max_prefill_s_if_only_prefill_pays_rest=prefill - rest,
            )
    if len(work) != 1:
        raise ValueError("different work between arms")
    return dict(status="CONDITIONAL_PHASE_BUDGET", order_source_sha256=AUTHORITY, arms=out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--orders", type=Path, default=Path(__file__).with_name("evidence") / "ordens.json"
    )
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = screen(a.orders)
    with (a.new_output_dir / "result.json").open("x") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(result["status"])
