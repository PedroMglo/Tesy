"""Select complete wave-0 producer bursts from a checked C135 journal."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIBLING = HERE.parent / "nvme_admission/io_pair"
sys.path.insert(0, str(SIBLING))
import plan as decode_plan  # noqa: E402


def key(r):
    return tuple(r[k] for k in ("layer", "expert", "slot", "generation"))


def make(trace, inventory, historical, backend):
    p = decode_plan
    require = p.require
    for path, sha in [(trace, p.TRACE), (historical, p.RECEIPT), (inventory, p.INVENTORY_SHA)]:
        require(p.sha256(path) == sha, "input digest")
    for name, sha in p.SOURCES.items():
        require(p.sha256(backend / name) == sha, "backend source")
    require(json.loads(historical.read_text())["trace_sha256"] == p.TRACE, "historical receipt")
    p.validate(trace)
    layers, all_rows = p.trace_rows(trace)
    rows = [r for r in all_rows if r["call_id"] == 2]
    first = {}
    groups = defaultdict(list)
    tile = -1
    prev_layer = 36
    wave = kind = None
    for r in rows:
        typ = r["kind"]
        if typ == "DEMAND":
            if r["layer"] < prev_layer:
                tile += 1
            prev_layer = r["layer"]
            wave = r["wave"]
            kind = "demand"
        elif typ == "PRELOAD":
            require(r["wave"] == wave + 1, "wrong preload wave")
            kind = "preload"
        elif typ == "ENQUEUE" and key(r) not in first:
            require(kind is not None, "unknown producer")
            first[key(r)] = r["seq"]
            groups[(tile, prev_layer, wave)].append((key(r), kind, r["seq"]))
    require(len(first) == 1177, "call-148 conservation")
    chosen = []
    objects = [json.loads(line) for line in inventory.read_text().splitlines()]
    require(objects[0]["tensor_count"] == len(objects) - 1 == 687, "inventory size")
    tensors = {x["name"]: x for x in objects[1:]}
    for tier in ("CPU", "CUDA0"):
        for (tile, layer, wave), jobs in sorted(groups.items()):
            demand_ids = [k[1] for k, role, _ in jobs if role == "demand"]
            if (
                wave != 0
                or layers[layer]["device"] != tier
                or len(demand_ids) < 8
                or demand_ids == sorted(demand_ids)
            ):
                continue
            roles = [k for _, k, _ in jobs]
            require(roles == sorted(roles), "demand/preload interleaved")
            ids = {k for k, _, _ in jobs}
            which = [r for r in rows if key(r) in ids]
            dequeue = [r for r in which if r["kind"] == "DEQUEUE"]
            require([key(r) for r in dequeue] == [k for k, _, _ in jobs], "native FIFO differs")
            require(jobs[-1][-1] < dequeue[0]["seq"], "cohort not fully released")
            last_end = max(r["seq"] for r in which if r["kind"] == "LOAD_END")
            block = [r for r in rows if dequeue[0]["seq"] <= r["seq"] <= last_end]
            require(
                all(
                    key(r) in ids
                    for r in block
                    if r["kind"] in {"LOAD_BEGIN", "LOAD_END", "DEQUEUE"}
                ),
                "foreign service",
            )
            e = []
            for k, role, seq in jobs:
                reads = [r for r in which if key(r) == k and r["kind"] == "READ_BEGIN"]
                require([r["component"] for r in reads] == [0, 1, 2], "native components")
                ranges = []
                for r, component in zip(reads, p.COMPONENTS, strict=True):
                    t = tensors[f"blk.{layer}.ffn_{component}_exps.weight"]
                    require(
                        t["tensor_type"] == "mxfp4"
                        and t["shape"] == [2880, 2880, 128]
                        and t["n_bytes"] == 128 * p.SIZE
                        and r["logical_bytes"] == p.SIZE,
                        "tensor geometry",
                    )
                    offset = t["data_offset"] + k[1] * p.SIZE
                    aligned = offset // p.ALIGN * p.ALIGN
                    length = (offset - aligned + p.SIZE + p.ALIGN - 1) // p.ALIGN * p.ALIGN
                    require(aligned + length <= 63_387_346_208, "EOF")
                    ranges.append([offset, p.SIZE, aligned, length])
                e.append(
                    dict(
                        layer=layer,
                        expert=k[1],
                        slot=k[2],
                        generation=k[3],
                        role=role,
                        enqueue_seq=seq,
                        ranges=ranges,
                    )
                )
            chosen.append(
                dict(
                    layer=layer,
                    tier=tier,
                    tile=tile,
                    wave=wave,
                    jobs=e,
                    first_dequeue_seq=dequeue[0]["seq"],
                    last_load_end_seq=last_end,
                )
            )
            break
    require(
        [(x["layer"], len(x["jobs"])) for x in chosen] == [(14, 21), (25, 11)], "frozen selection"
    )
    return dict(
        schema="c135-prefill-eligible-queue-1",
        groups=chosen,
        trace_sha256=p.TRACE,
        inventory_sha256=p.INVENTORY_SHA,
        trace_source_sha256=p.SOURCES,
        historical_receipt_sha256=p.RECEIPT,
        component_order=p.COMPONENTS,
        aligned_bytes_per_arm=sum(r[3] for g in chosen for j in g["jobs"] for r in j["ranges"]),
        payload_bytes_per_arm=32 * 3 * p.SIZE,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "inventory", "historical", "backend", "new-plan"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    result = make(a.trace, a.inventory, a.historical, a.backend)
    with a.new_plan.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
