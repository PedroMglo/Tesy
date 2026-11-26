"""Compare full-pack and compact-file observations after both processes have exited."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
suite = run_path(str(HERE / "measure.py"))
ref = run_path(str(HERE.parent / "t1_native_sink/review.py"))
need, read = ref["need"], ref["read"]


def review(a):
    seal = read(ref["RAM"] / "plan-receipt.json", ref["bench"]["SEAL"])
    plan = read(a.plan, ref["bench"]["PLAN"])
    costs, prep_bytes = ref["plan_costs"](plan, seal)
    pack = suite["FullPack"](a.placement, a.placement_sha256, offline=True)
    entries = ref["bench"]["checked_plan"](plan, seal)
    pack.bind(plan, seal, entries)
    baseline = read(a.ram_receipt, ref["BASE_SHA"])
    compact = read(suite["SINK"] / "evidence/receipt.json", suite["SLICE_REF"])
    static_map = read(a.map, ref["MAP_SHA"])
    arms = []
    raw = []
    for i, (directory, digest, gate) in enumerate(
        ((a.first, a.first_sha256, a.c55), (a.second, a.second_sha256, a.second_c55 or a.c55)), 1
    ):
        row = read(directory / "receipt.json", digest)
        need(
            row["status"] == "PASS_FULL_PACK_NATIVE_SINKS"
            and row["arm"] == i
            and row["full_pack_stat"] == pack.stat
            and row["selected_windows_sha256"] == baseline["partial_sha256"]
            and row["plan_sha256"] == ref["bench"]["PLAN"]
            and row["ram_receipt_sha256"] == ref["BASE_SHA"]
            and row["first_sha256"] == (None if i == 1 else a.first_sha256)
            and all(row[k] == v for k, v in pack.evidence.items())
            and all(
                row[k] == baseline[k] for k in ("model_stat", "monitor_provider", "arm_read_bytes")
            )
            and row["native"] == compact["native"]
            and row["gpu_transfers"] is True
            and row["transformer_forwards"] == 0,
            "full source, plan and provider identity",
        )
        ref["buffers"](row["native"], static_map)
        blocks = ref["journal"](directory / "raw/blocks.jsonl", row["block_sha256"])
        s = ref["service"](blocks, row, costs, prep_bytes)
        s["resources"] = ref["monitoring"](directory, row, gate)
        s.update(
            arm=i,
            receipt_sha256=digest,
            **{
                k: row[k]
                for k in (
                    "block_sha256",
                    "c55_sha256",
                    "monitor_sha256",
                    "prepare_ns",
                    "native_init_ns",
                    "fixture_cleanup_ns",
                )
            },
        )
        need(
            min(s[k] for k in ("prepare_ns", "native_init_ns", "fixture_cleanup_ns")) > 0,
            "complete preparation and cleanup",
        )
        arms.append(s)
        raw.append(row)
    passes = [s["passes"] for s in arms]
    need(
        raw[0]["unit"] != raw[1]["unit"]
        and raw[0]["commit"] == raw[1]["commit"]
        and raw[0]["tree"] == raw[1]["tree"]
        and raw[1]["both_processes_pass"] == all(passes),
        "independent same-build processes",
    )
    compact_timings = [
        {
            k: {"medians_ms": v["median_ms"], "contrasts": v["effects"]}
            for k, v in arm["timing"].items()
        }
        for arm in compact["arms"]
    ]
    return {
        "status": "GO_COST_42_STRATA"
        if all(passes)
        else "INCONCLUSIVE"
        if any(passes)
        else "NO_GO_EXPANSION",
        "commit": raw[0]["commit"],
        "tree": raw[0]["tree"],
        "full_pack_sha256": suite["PACK"],
        "placement_sha256": a.placement_sha256,
        "offsets_sha256": pack.evidence["offsets_sha256"],
        "selected_windows_sha256": baseline["partial_sha256"],
        "samples": 4,
        "records": 29,
        "components": 87,
        "arms": arms,
        "compact_reference_sha256": suite["SLICE_REF"],
        "compact_processes": compact_timings,
        "per_cell_per_stratum": costs,
        "transformer_forwards": 0,
        "scope": "The two earlier compact-file processes are independent historical comparators. "
        "Each within-process contrast is paired; cross-epoch wall times are descriptive.",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "first",
        "second",
        "plan",
        "map",
        "ram-receipt",
        "placement",
        "c55",
        "second-c55",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=arg != "second-c55")
    for name in ("first-sha256", "second-sha256", "placement-sha256"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = review(a)
    except Exception as exc:
        (a.new_output_dir / "receipt.json").write_text(
            json.dumps({"status": "FAIL_PRESERVED", "reason": str(exc)}) + "\n"
        )
        raise
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(result["status"])
