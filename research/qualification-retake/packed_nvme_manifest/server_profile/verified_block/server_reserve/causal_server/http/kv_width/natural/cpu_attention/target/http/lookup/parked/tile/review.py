"""Reopen both FFN families, reconstruct exact wave maps and recalculate the paired prices."""

import argparse
import hashlib
import json
import statistics
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "study.py"))
need, sha, read = (S[k] for k in ("need", "sha", "read"))
EXPECTED = {
    "build": "c7f041bd70a6e37a50b00fd710e1c8477948d6c5063a6c07974cde5b2332a5ae",
    "exact": "af7cc6b11d4677a7f63d153d132ce4af60367cba300c0ac4f8aaf2abf715bb82",
    "price": "84c9ccd806189437a44e472328eb7ab6cecaf3a3c28d5bcdec28f9651fd54f9c",
}


def audit(root, inputs):
    S["verify_input"](inputs)
    tile = (inputs / "ffn_moe_out-0.bin").read_bytes()[32 * 2880 * 4 : 64 * 2880 * 4]
    routes = struct.unpack_from("<128i", (inputs / "ffn_moe_topk-0.bin").read_bytes(), 32 * 4 * 4)
    families = {}
    for phase, pin in EXPECTED.items():
        folder = root / f"tesy-c266-parked-{phase}-20261126-r02"
        need(sha(folder / "receipt.json") == pin, "closed " + phase)
        families[phase] = folder
    build = read(families["build"] / "receipt.json")
    need(
        sha(families["build"] / "fixture") == build["binary_sha256"]
        and sha(families["build"] / "stock") == build["stock_sha256"],
        "both executables",
    )
    stock = read(families["exact"] / "1-STOCK.json")
    slots = stock["slots"]
    need(
        len(slots["owners"]) == 40
        and sum(e >= 0 for e in slots["owners"]) == 5
        and not any(slots["claims"]),
        "primary bank",
    )
    cold = {"reads": 5, "returned_bytes": 66109440, "set_bytes": 66096000, "sets": 15}
    maps = bytearray()
    for w in range(8):
        physical = [slots["owners"].index(e) for e in routes] if w == 0 else [-1] * 128
        maps.extend(struct.pack("<128i", *physical))
        maps.extend(struct.pack("<128I", *([0x3F800000 if w == 0 else 0] * 128)))
    result = []
    for phase in ("exact", "price"):
        folder = families[phase]
        family = read(folder / "receipt.json")
        need(
            family["commit"] == build["commit"] and family["build_sha256"] == EXPECTED["build"],
            "same build",
        )
        need(tuple(a["arm"] for a in family["arms"]) == S["ORDERS"][phase], "order")
        for row in family["arms"]:
            name = row["name"]
            native = read(folder / (name + ".json"))
            need(
                sha(folder / (name + ".json")) == row["native_sha256"]
                and native["slots"] == slots
                and native["cold"] == cold
                and native["joined_workers"] == 4
                and native["manager_destructor_returned"]
                and (folder / name / "tile.f32").read_bytes() == tile
                and native["backend_splits"] == 1,
                "independent FFN, drain and resources",
            )
            if row["arm"] != "STOCK":
                need(
                    (folder / name / "wave-maps.bin").read_bytes() == maps,
                    "all 1,024 physical IDs and mask words",
                )
                if row["arm"] == "OFF":
                    need(
                        native["graph_fingerprint"] == stock["graph_fingerprint"],
                        "reference graph shape",
                    )
            if phase == "price":
                elapsed = native["times_ns"]
                need(
                    len(elapsed) == 7 and min(elapsed) > 0 and elapsed == row["times_ns"],
                    "complete wall clocks",
                )
                median = statistics.median(elapsed)
                need(
                    median == row["median_ns"] and native["build_ns"] == row["build_ns"],
                    "individual price",
                )
                result.append(
                    dict(
                        arm=row["arm"],
                        median_ns=median,
                        range_ns=[min(elapsed), max(elapsed)],
                        samples_ns=elapsed,
                        build_ns=native["build_ns"],
                        nodes=native["graph_nodes"],
                        mmids=native["mmids"],
                    )
                )
    pairs = []
    for off, on in ((result[0], result[1]), (result[3], result[2])):
        gain = off["median_ns"] - on["median_ns"]
        pairs.append(
            dict(hot_gain_ns=gain, with_build_gain_ns=gain + off["build_ns"] - on["build_ns"])
        )
    need(pairs == read(families["price"] / "receipt.json")["pairs"], "paired calculation")
    allowed = min(p["with_build_gain_ns"] for p in pairs)
    status = (
        "GO_BOUNDARY_FIXTURE"
        if allowed > 0 and all(p["hot_gain_ns"] > 0 for p in pairs)
        else "INCONCLUSIVE"
    )
    return dict(
        status=status,
        commit=build["commit"],
        tree=build["tree"],
        inputs_sha256=EXPECTED,
        matched=7,
        routed_positions=32,
        ffn_values=92160,
        output_sha256=hashlib.sha256(tile).hexdigest(),
        wave_maps_sha256=hashlib.sha256(maps).hexdigest(),
        banks_equal=True,
        cold_per_process=cold,
        samples_per_timed_process=7,
        arms=result,
        pairs=pairs,
        additional_boundary_allowance_ns=allowed,
        full_model_starts=0,
        new_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "input", "new-output-dir"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    data = audit(a.root, a.input)
    with (a.new_output_dir / "result.json").open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
