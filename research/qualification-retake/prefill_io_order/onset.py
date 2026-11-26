"""Post-hoc comparison of the first four gate reads and preceding historical I/O."""

import argparse
import json
from pathlib import Path

from make_plan import decode_plan as native
from measure import HERE, ORDER, io, require


def evidence(raw, trace):
    reference = json.loads((HERE / "evidence-20261125-r1/receipt.json").read_text())
    schedule = json.loads((HERE / "schedule.json").read_text())
    require(io.sha256(trace) == native.TRACE, "C135 input")
    native.validate(trace)
    _, rows = native.trace_rows(trace)
    rows = [e for e in rows if e["call_id"] == 2]
    gate = schedule["groups"][0]
    start = gate["first_dequeue_seq"]
    last = gate["last_load_end_seq"]
    previous = [e for e in rows if e["seq"] < start and e["kind"] == "READ_END"]
    prev = max(previous, key=lambda e: e["mono_us"])
    new = min(e["mono_us"] for e in rows if start < e["seq"] <= last and e["kind"] == "READ_BEGIN")
    require(prev["layer"] == 13 and gate["layer"] == 14, "unexpected preceding layer")
    arms = []
    for i, mode in enumerate(ORDER, 1):
        name = f"arm-{i}-{mode}.json"
        require(io.sha256(raw / name) == reference["raw_manifest"][name]["sha256"], "arm digest")
        group = json.loads((raw / name).read_text())["groups"][0]
        j = [group["jobs"][k] for k in group["order_indices"][:4]]
        spans = [x["read_spans_ns"][0] for x in j]
        require(len(j) == 4 and len({x["worker_id"] for x in j}) == 4, "first four reads")
        arms.append(
            dict(
                arm=i,
                mode=mode,
                layer=group["layer"],
                experts=[x["expert"] for x in j],
                worker_read_sum_ns=sum(b - a for a, b in spans),
                elapsed_first_start_to_last_return_ns=max(b for _, b in spans)
                - min(a for a, _ in spans),
            )
        )
    return dict(
        classification="DIAGNOSTICO_POST_HOC",
        arms=arms,
        c135_sha256=native.TRACE,
        preceding_call2_read_completions=len(previous),
        preceding_call2_completed_experts=len(
            {(e["layer"], e["expert"], e["slot"], e["generation"]) for e in previous}
        ),
        preceding_expert=prev["expert"],
        preceding_layer=prev["layer"],
        preceding_component=prev["component"],
        last_read_end_to_first_read_begin_us=new - prev["mono_us"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-dir", "trace", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    result = evidence(a.raw_dir, a.trace)
    a.new_output_dir.mkdir(exist_ok=False)
    io.save(a.new_output_dir / "receipt.json", result)
