"""Re-evaluate the archived CPU tile without loading GGML or the model."""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"
REFERENCE = "b3db7c58b1aeac0c40a26131e89009793f04e0c16a8275f23e7238f55339a7b2"
BUILD_PASS = "PASS_C269_PARKED_MMID_BUILD"
RUN_PASS = "PASS_PARKED_MMID_TILE_FAMILY"


def need(condition, why):
    if not condition:
        raise ValueError(why)


def digest(path):
    need(path.is_file() and not path.is_symlink(), "expected regular file: " + path.name)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path, sha):
    need(digest(path) == sha, "file identity: " + path.name)
    return json.loads(path.read_bytes())


def compact(root, build_dir, terminal_sha, build_sha):
    top = read(root / "receipt.json", terminal_sha)
    build = read(build_dir / "receipt.json", build_sha)
    need(build["status"] == BUILD_PASS and top["status"] in (RUN_PASS, "FAIL_PRESERVED"), "status")
    result = dict(
        status=top["status"],
        build_sha256=build_sha,
        terminal_sha256=terminal_sha,
        family_wall_s=top["elapsed_s"],
    )
    if top["status"] != RUN_PASS:
        result["reason"] = top.get("reason")
        if top.get("detail_sha256"):
            partial = read(root / "detail.json", top["detail_sha256"])
            result["preserved_arms"] = [
                {k: row.get(k) for k in ("run_index", "mode", "status", "child_started")}
                for row in partial["arms"]
            ]
        return result

    detail = read(root / "detail.json", top["detail_sha256"])
    ref = read(HERE.parent / "cpu0_suffix/physical-r01/receipt.json", REFERENCE)
    need(
        top["scope_rc"] == 0 and detail["status"] == RUN_PASS and top["arms_started"] == 11,
        "scope closure",
    )
    need(
        detail["build_sha256"] == build_sha
        and detail["cpu0_compact_sha256"] == REFERENCE
        and detail["executable_sha256"] == ref["executable_sha256"] == build["binary_sha256"],
        "build or reference",
    )
    for source in ("protocol.md", "decision.py", "profile.py"):
        need(digest(HERE / source) == detail["source_sha256"][source], "frozen " + source)
    need(detail["numerical_fixture_sha256"] == build["numerical_fixture_sha256"], "fixture")
    spec = importlib.util.spec_from_file_location("parked_decision", HERE / "decision.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    rows = []
    order = ("ORIGINAL", "OFF", "ON", *gate.ORDER)
    for i, (mode, row) in enumerate(zip(order, detail["arms"], strict=True)):
        folder = root / f"{i:02d}-{mode}"
        local = json.loads((folder / "receipt.json").read_bytes())
        need(
            local == row
            and row["run_index"] == i
            and row["mode"] == mode
            and row["phase"] == ("qualification" if i < 3 else "timing")
            and row["returncode"] == 0
            and row["child_started"] is True
            and row["status"] == "PASS_PARKED_MMID_TILE_ARM",
            "arm identity",
        )
        native = read(folder / "stdout", row["stdout_sha256"])
        need(digest(folder / "stderr") == row["stderr_sha256"], "arm stderr")
        tile = folder / "native/tile.f32"
        need(
            digest(tile) == row["tile_sha256"] == GOLD and tile.stat().st_size == 368640,
            "numerical output",
        )
        want_cpu = build["original_cpu_sha256" if mode == "ORIGINAL" else "candidate_cpu_sha256"]
        expected = {"cpu": want_cpu, "base": build["base_sha256"]}
        need(
            row["provider_sha256"] == expected
            and all(detail["providers"][mode][r]["sha256"] == sha for r, sha in expected.items())
            and row["kernel_env"] == {"ORIGINAL": None, "OFF": "0", "ON": "1"}[mode],
            "provider",
        )
        need(
            native["graph_start_ns"] == row["start_ns"] < row["end_ns"] == native["graph_end_ns"]
            and row["end_ns"] - row["start_ns"] == native["graph_ns"] == row["graph_ns"]
            and native["clock"] == "CLOCK_MONOTONIC"
            and native["mode"] == row["observer"] == "OFF"
            and native["wave_return_ns"] is None
            and native["wave_markers"] == 0
            and native["cb_eval_registered"] is False,
            "clock or graph observer",
        )
        for key in ("graph_fingerprint", "graph_nodes", "backend_splits"):
            need(native[key] == row[key] == ref[key], "graph identity: " + key)
        for key, target in dict(
            graph_mmid_nodes=24,
            wave_calls=8,
            active_waves=1,
            unique_loads=5,
            expected_pread_bytes=66109440,
            logical_weight_bytes=66096000,
            expected_weight_sets=15,
            joined_workers=4,
        ).items():
            need(native[key] == row[key] == target, "work: " + key)
        rows.append(
            {
                k: row[k]
                for k in (
                    "run_index",
                    "phase",
                    "mode",
                    "graph_ns",
                    "tile_sha256",
                    "stdout_sha256",
                    "stderr_sha256",
                )
            }
        )
    assessment = gate.evaluate(rows[3:])
    need(assessment == detail["assessment"] == top["assessment"], "decision")
    inv = detail["c118"]
    unit = top["unit"]
    need(re.fullmatch(r"tesy-[a-z0-9-]+", unit) is not None, "unit")
    inventory = root / "raw" / (unit + ".start-inventory.jsonl")
    need(
        digest(inventory) == inv["sha256"]
        and inv["duration_s"] >= 60
        and len(inventory.read_bytes().splitlines()) == inv["sample_count"],
        "C118",
    )
    monitor = root / "raw/samples.jsonl"
    need(digest(monitor) == detail["monitor_sha256"], "resource monitor")
    samples = [json.loads(line) for line in monitor.read_bytes().splitlines()]
    need(
        len(samples) == detail["monitor_samples"] >= 2
        and all(not sample["compute_pids"] and sample["gap_s"] <= 3 for sample in samples),
        "coverage",
    )
    need(
        detail["swap_peak_bytes"] == detail["child_processes_at_cleanup"] == 0
        and detail["peak_bytes"] < 3584 * 2**20
        and detail["total_output_bytes"] == 11 * 368640
        and detail["expected_aligned_service_bytes"] == 11 * 66109440
        and detail["logical_service_bytes"] == 11 * 66096000,
        "family totals",
    )
    result.update(
        assessment=assessment,
        arms=rows,
        detail_sha256=top["detail_sha256"],
        original_cpu_sha256=build["original_cpu_sha256"],
        candidate_cpu_sha256=build["candidate_cpu_sha256"],
        base_sha256=build["base_sha256"],
        c118={k: inv[k] for k in ("duration_s", "sample_count", "sha256")},
    )
    for k in (
        "commit",
        "tree",
        "input_sha256",
        "pack_sha256",
        "source_sha256",
        "numerical_fixture_sha256",
        "c55_sha256",
        "monitor_samples",
        "monitor_sha256",
        "peak_bytes",
        "swap_peak_bytes",
        "expected_aligned_service_bytes",
        "logical_service_bytes",
        "total_output_bytes",
        "child_processes_at_cleanup",
    ):
        result[k] = detail[k]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for opt in ("raw-root", "build-dir", "new-output-dir"):
        parser.add_argument("--" + opt, type=Path, required=True)
    for opt in ("receipt-sha256", "build-sha256"):
        parser.add_argument("--" + opt, required=True)
    args = parser.parse_args()
    receipt = compact(args.raw_root, args.build_dir, args.receipt_sha256, args.build_sha256)
    args.new_output_dir.mkdir(mode=0o700)
    with (args.new_output_dir / "receipt.json").open("x") as out:
        json.dump(receipt, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
