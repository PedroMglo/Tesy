"""Derive the exact C135 call-3 read plan from verified journals and native GGUF inventory."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "tools"))
from c122_trace_validate import validate  # noqa: E402
from c123_analyze_trace import trace_rows  # noqa: E402
from c125_component_io_probe import ALIGN, INVENTORY_SHA  # noqa: E402
from run_bounded import sha256  # noqa: E402

TRACE = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
RECEIPT = "1a096a2f2d0be1b3c18f0490f5d667fb5dee4035275a28390b1dab5f2cb6dd43"
SOURCES = {
    "src/llama-moe-stream.cpp": "b7ca5f9608f4c20140a51748f88ff64657c0d586f0edc527d4cabd5fd39f2d4c",
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
}
COMPONENTS = ("gate", "down", "up")
SIZE = 4_406_400


def require(ok, why):
    if not ok:
        raise ValueError(why)


def make_plan(trace, historical, inventory, backend):
    for path, digest in ((trace, TRACE), (historical, RECEIPT), (inventory, INVENTORY_SHA)):
        require(sha256(path) == digest, f"wrong {path.name} digest")
    require(json.loads(historical.read_text())["trace_sha256"] == TRACE, "trace receipt mismatch")
    for name, digest in SOURCES.items():
        require(sha256(backend / name) == digest, "source changed " + name)
    checked = validate(trace)
    calls = checked["calls"]
    call = calls.get(3, calls.get("3"))
    require(
        (call["n_tokens"], call["first_pos"], call["last_pos"]) == (1, 2197, 2197),
        "wrong decode call",
    )
    tensors = [json.loads(line) for line in inventory.read_text().splitlines()]
    require(tensors[0]["tensor_count"] == len(tensors) - 1 == 687, "inventory cardinality")
    by_name = {t["name"]: t for t in tensors[1:]}
    _, rows = trace_rows(trace)
    job = [r for r in rows if r["call_id"] == 3]
    queue = [r for r in job if r["kind"] == "ENQUEUE"]

    def identity(r):
        return r["layer"], r["expert"], r["slot"], r["generation"]

    require(len(queue) == len(set(map(identity, queue))) == 20, "queue identity count")
    require(
        list(map(identity, queue)) == [identity(r) for r in job if r["kind"] == "DEQUEUE"],
        "FIFO mismatch",
    )
    plan = []
    for layer in sorted(set(r["layer"] for r in queue)):
        q = [r for r in queue if r["layer"] == layer]
        early = [r["mono_us"] for r in q]
        end = [r for r in job if r["layer"] == layer and r["kind"] == "WAIT_END"]
        require(
            len(end) == 1 and (not plan or plan[-1]["wait_end_us"] < min(early)),
            "cross-layer barrier invalid",
        )
        group = dict(layer=layer, wait_end_us=end[0]["mono_us"], experts=[])
        for enqueue in q:
            match = [r for r in job if identity(r) == identity(enqueue)]
            reads = [r for r in match if r["kind"] == "READ_BEGIN"]
            require([r["component"] for r in reads] == [0, 1, 2], "expert component order")
            span = [r for r in match if r["kind"] == "LOAD_END"]
            require(
                len(span) == 1 and span[0]["mono_us"] <= group["wait_end_us"], "missing layer drain"
            )
            ranges = []
            for r, component in zip(reads, COMPONENTS, strict=True):
                name = f"blk.{layer}.ffn_{component}_exps.weight"
                t = by_name[name]
                require(
                    t["shape"] == [2880, 2880, 128]
                    and t["tensor_type"] == "mxfp4"
                    and t["n_bytes"] == 128 * SIZE
                    and r["logical_bytes"] == SIZE,
                    name,
                )
                offset = t["data_offset"] + r["expert"] * SIZE
                aligned = offset // ALIGN * ALIGN
                count = ((offset - aligned + SIZE + ALIGN - 1) // ALIGN) * ALIGN
                require(aligned + count <= 63_387_346_208, "aligned read exceeds EOF")
                ranges.append([offset, SIZE, aligned, count])
            group["experts"].append(
                dict(
                    expert=enqueue["expert"],
                    slot=enqueue["slot"],
                    generation=enqueue["generation"],
                    ranges=ranges,
                )
            )
        plan.append(group)
    require(
        len(plan) == 16
        and sum(len(g["experts"]) for g in plan) == 20
        and max(len(g["experts"]) for g in plan) == 4,
        "schedule cardinality",
    )
    return dict(
        schema="tesy-c135-first-decode-io-v1",
        call=3,
        position=2197,
        trace_sha256=TRACE,
        inventory_sha256=INVENTORY_SHA,
        historical_receipt_sha256=RECEIPT,
        source_sha256=SOURCES,
        loads=20,
        logical_bytes=60 * SIZE,
        aligned_bytes=sum(r[3] for g in plan for e in g["experts"] for r in e["ranges"]),
        component_order=COMPONENTS,
        groups=plan,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "historical", "inventory", "backend", "new-plan"):
        ap.add_argument("--" + name, required=True, type=Path)
    a = ap.parse_args()
    plan = make_plan(a.trace, a.historical, a.inventory, a.backend)
    with a.new_plan.open("x") as out:
        json.dump(plan, out, sort_keys=True, indent=2)
        out.write("\n")
