"""Recheck a closed CPU0 suffix family from archived raw files, without the original runtime."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BUILD_SHA = "37f7ceec65cab37640dbf4b5b1f48bec19165d097a84adbfb956a01ea7db1f13"
DECISION = "87052fa03aebcf5ce17c388bceb9bc063acf33fc573ff6b2b6be47a3ab8bde7f"
PROFILE = "64c526583837b485564003eb92f398117e99dcd9f5304788aa0a4d1bebb2745e"
PROTOCOL = "c3a6101ae9c1c058b0a8488a7b4c4e18b8e99f093cce00fb606a271ce48cf155"
GOLD = "bf0391c5e7aad2aa22c730d56c07213fadcd0db1b7801d5dd58e1533f9aaba24"
C55 = "fefa2098a5ce89b5a438b6c49fb544acfb9baa974278a027fea850de3cb7790a"
COMMIT = "e6e63160465a11fc4404809d7e217fe2a761db1b"
TREE = "a407df0ea40d59cdfb41409ea6cad6cc46abe10c"
PASS = "PASS_CPU0_SUFFIX_TIMING_FAMILY"


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path, wanted):
    need(not path.is_symlink() and digest(path) == wanted, "changed evidence: " + path.name)
    return json.loads(path.read_bytes())


def compact(repo, root, build_dir, receipt_sha):
    top = read(root / "receipt.json", receipt_sha)
    need(
        top["status"] in {"FAIL_PRESERVED", PASS} and top["supervisor_sha256"] == PROFILE,
        "nonterminal or foreign family",
    )
    build = read(build_dir / "receipt.json", BUILD_SHA)
    ck = dict(
        status=top["status"],
        receipt_sha256=receipt_sha,
        build_sha256=BUILD_SHA,
        family_wall_s=top["elapsed_s"],
        failed=top["status"] != "PASS_CPU0_SUFFIX_TIMING_FAMILY",
        arms=[],
        scope_rc=top.get("scope_rc"),
        detail_sha256=top.get("detail_sha256"),
    )
    if not (root / "detail.json").exists():
        need(ck["failed"], "successful run without detail")
        ck["last_stage"] = "NO_COMPLETE_SCOPE_RECEIPT"
        return ck
    detail = read(root / "detail.json", top["detail_sha256"])
    if ck["failed"]:
        ck["last_stage"] = "SCOPE_FAILED"
        ck["preserved_arms"] = [
            {
                "run_index": r["run_index"],
                "status": r["status"],
                "child_started": r["child_started"],
                "stdout_sha256": r.get("stdout_sha256"),
                "stderr_sha256": r.get("stderr_sha256"),
            }
            for r in detail["arms"]
        ]
        ck["failure_sha256"] = hashlib.sha256(str(detail.get("failure")).encode()).hexdigest()
        return ck
    need(
        build["status"] == "PASS_C291_CPU0_SUFFIX_BUILD"
        and build["commit"] == detail["commit"] == COMMIT
        and build["tree"] == detail["tree"] == TREE
        and detail["status"] == PASS
        and detail["build_sha256"] == BUILD_SHA,
        "build/measure identity",
    )
    need(
        top["scope_rc"] == 0
        and top["arms_started"] == 8
        and detail["supervisor_sha256"] == PROFILE
        and detail["c55_sha256"] == C55,
        "scope and admission",
    )
    study = repo / "research/qualification-retake/cpu0_suffix"
    need(
        digest(study / "decision.py") == detail["source_sha256"]["decision.py"] == DECISION
        and detail["source_sha256"]["protocol.md"] == PROTOCOL,
        "evaluator",
    )
    spec = importlib.util.spec_from_file_location("cpu0_suffix_decision", study / "decision.py")
    decide = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decide)
    for i, (row, mode) in enumerate(zip(detail["arms"], decide.ORDER, strict=True)):
        folder = root / f"{i:02d}-{mode}"
        local = read(folder / "receipt.json", digest(folder / "receipt.json"))
        need(
            row == local
            and row["run_index"] == i
            and row["observer"] == mode
            and row["child_started"]
            and row["returncode"] == 0
            and row["status"] == "PASS_C291_CPU0_SUFFIX_ARM",
            "child identity",
        )
        stdout, stderr = folder / "stdout", folder / "stderr"
        native = read(stdout, row["stdout_sha256"])
        need(digest(stderr) == row["stderr_sha256"], "stderr")
        tile = folder / "native/tile.f32"
        need(
            tile.stat().st_size == 92160 * 4 and digest(tile) == row["tile_sha256"] == GOLD,
            "tile size or SHA",
        )
        need(
            native["status"] == "PASS_C291_CPU0_SUFFIX"
            and native["clock"] == "CLOCK_MONOTONIC"
            and native["mode"] == mode
            and native["cb_eval_registered"] is False
            and native["compute_backend"] == "CPU"
            and native["arm"] == "DENSE",
            "native boundaries",
        )
        need(
            native["graph_start_ns"] == row["start_ns"]
            and native["wave_return_ns"] == row["return_ns"]
            and native["graph_end_ns"] == row["end_ns"]
            and native["graph_ns"] == row["graph_ns"] == row["end_ns"] - row["start_ns"],
            "graph clock",
        )
        need(
            native["suffix_ns"] == row["suffix_ns"] and native["wave_markers"] == int(mode == "ON"),
            "suffix clock count",
        )
        if mode == "ON":
            need(
                type(native["marked_graph_threads"]) is int
                and 1 <= native["marked_graph_threads"] <= 8
                and row["start_ns"] < row["return_ns"] < row["end_ns"]
                and row["suffix_ns"] == row["end_ns"] - row["return_ns"],
                "ON marker",
            )
        else:
            need(
                native["marked_graph_threads"] == 0
                and row["return_ns"] is None
                and row["suffix_ns"] is None,
                "OFF marker",
            )
        for k, v in dict(
            graph_mmid_nodes=24,
            router_positions=153,
            ffn_positions=32,
            full_ffn_values=92160,
            wave_calls=8,
            graph_waves=8,
            active_waves=1,
            unique_loads=5,
            expected_weight_sets=15,
            expected_pread_bytes=66109440,
            logical_weight_bytes=66096000,
            joined_workers=4,
        ).items():
            need(native[k] == v, "native work:" + k)
        for k in ("graph_nodes", "graph_fingerprint", "backend_splits"):
            need(native[k] == row[k], "native graph identity:" + k)
        ck["arms"].append(
            {
                k: row[k]
                for k in (
                    "run_index",
                    "observer",
                    "graph_ns",
                    "suffix_ns",
                    "tile_sha256",
                    "stdout_sha256",
                    "stderr_sha256",
                )
            }
            | dict(
                tile_bytes=tile.stat().st_size, marked_graph_threads=native["marked_graph_threads"]
            )
        )
    assessment = decide.evaluate(ck["arms"])
    need(assessment == detail["assessment"] == top["assessment"], "decision reproduction")
    samples = root / "raw/samples.jsonl"
    need(digest(samples) == detail["monitor_sha256"], "monitor digest")
    telemetry = [json.loads(line) for line in samples.read_bytes().splitlines()]
    need(
        len(telemetry) == detail["monitor_samples"] >= 2
        and all(not t["compute_pids"] and t["gap_s"] <= 3 for t in telemetry),
        "telemetry coverage",
    )
    need(
        detail["swap_peak_bytes"] == detail["child_processes_at_cleanup"] == 0
        and detail["peak_bytes"] < 3584 * 2**20
        and detail["expected_aligned_service_bytes"] == 8 * 66109440
        and detail["logical_service_bytes"] == 8 * 66096000,
        "family closure",
    )
    inv = detail["c118"]
    sample_path = root / "raw" / (top["unit"] + ".start-inventory.jsonl")
    need(
        digest(sample_path) == inv["sha256"]
        and len(sample_path.read_bytes().splitlines()) == inv["sample_count"]
        and inv["duration_s"] >= 60,
        "C118 closure",
    )
    ck.update(
        assessment=assessment,
        **{
            k: detail[k]
            for k in (
                "commit",
                "tree",
                "build_sha256",
                "source_sha256",
                "input_sha256",
                "pack_sha256",
                "numerical_gate_sha256",
                "c55_sha256",
                "peak_bytes",
                "swap_peak_bytes",
                "child_processes_at_cleanup",
                "expected_aligned_service_bytes",
                "logical_service_bytes",
                "prepared_pack_bytes",
                "monitor_samples",
                "monitor_sha256",
                "executable_sha256",
                "provider_sha256",
                "monitor_provider",
            )
        },
        c118={k: inv[k] for k in ("duration_s", "sample_count", "sha256")},
        total_output_bytes=sum(arm["tile_bytes"] for arm in ck["arms"]),
        graph_nodes=detail["arms"][0]["graph_nodes"],
        graph_fingerprint=detail["arms"][0]["graph_fingerprint"],
        backend_splits=detail["arms"][0]["backend_splits"],
    )
    need(ck["total_output_bytes"] == 2949120, "output byte conservation")
    return ck


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "raw-root", "build-dir", "new-output-dir"):
        ap.add_argument("--" + arg, type=Path, required=True)
    ap.add_argument("--receipt-sha256", required=True)
    a = ap.parse_args()
    result = compact(a.repo, a.raw_root, a.build_dir, a.receipt_sha256)
    a.new_output_dir.mkdir(mode=0o700)
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
