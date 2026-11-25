"""Reproduce the layer-25 diagnostic from captured activations, without model weights."""

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("l25_reopen_observer", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
need, read, sha = profile.need, profile.read, profile.sha
grade = profile.load(HERE / "grade.py", "l25_reopened_grading")
CUTS = (
    "attn_post_norm-24",
    "ffn_moe_out-24",
    "attn_post_norm-25",
    "ffn_moe_logits-25",
    "ffn_moe_out-25",
)


def capture(family, arm):
    record = read(family / arm / "receipt.json")
    unit = record["unit"]
    need(Path(unit).name == unit, "arm unit")
    return family / arm / "raw" / (unit + ".capture")


def reopen(family, digest, integrated, archived, c270):
    need(sha(family / "receipt.json") == digest, "physical receipt hash")
    r = read(family / "receipt.json")
    need(
        r["status"] == "MEASURED_L25_INPUTS"
        and set(r["arms"]) == {"ON"}
        and r["model_launch_receipts"] == 1
        and r["protocol_sha256"] == profile.probes.PROTOCOL
        and r["historical_integrated_sha256"] == profile.probes.FAMILY_SHA,
        "completed ON and authority",
    )
    folder = family / "ON"
    arm = read(folder / "receipt.json")
    need(
        sha(folder / "receipt.json") == r["arms"]["ON"]["receipt_sha256"]
        and arm["status"] == "OBSERVED_ON"
        and arm["observer_neutral"] is True,
        "complete arm",
    )
    cap = capture(family, "ON")
    unit = arm["unit"]
    leaves = {
        folder / "loader-audit.json": "loader_sha256",
        folder / "command.json": "command_sha256",
        folder / "integrated-resource.json": "resource_sha256",
        folder / "comparison.json": "comparison_sha256",
        cap.parent / (unit + ".json"): "monitor_sha256",
        cap.parent / (unit + ".launch.json"): "launch_sha256",
        cap.parent / (unit + ".start-inventory.jsonl"): "c118_sha256",
    }
    need(all(sha(path) == arm[key] for path, key in leaves.items()), "physical witnesses")
    actual = grade.compare(cap, capture(integrated, "ON"), c270, capture(archived, "AR"))
    report = read(folder / "comparison.json")
    need(
        all(value == report[key] for key, value in actual.items())
        and r["diagnosis"] == actual["diagnosis"]
        and set(report) == set(actual) | set(profile.AR_DIAGNOSTICS),
        "reproduced arrays and inference",
    )
    prior = read(integrated / "ON/comparison.json")
    need(
        all(report[key] == prior[key] for key in profile.AR_DIAGNOSTICS)
        and prior["first"] == grade.integrated.frontiers(prior["comparisons"]),
        "inherited AR diagnosis on earlier cuts",
    )
    paired = {(row["position"], row["tensor"]): row for row in prior["comparisons"]}
    for row in actual["gold_rows"].values():
        row = row | {"tensor": f"{row['site']}-{row['layer']}"}
        key = row["position"], row["tensor"]
        need(
            key not in paired or paired[key] == row,
            "same archived and new product at a shared cut",
        )
        paired[key] = row
    first = grade.integrated.frontiers(list(paired.values()))
    compact = {
        k: actual[k]
        for k in (
            "diagnosis",
            "coverage",
            "identical_prior_on_payloads",
            "identical_common_ar_payloads",
            "prefill",
            "state_sha256",
            "logits_sha256",
            "pos191",
        )
    }
    strata = {}
    for pos in (189, 190):
        rows = {name: actual["gold_rows"][f"{pos}.{name}"] for name in CUTS}
        sites = [r["tensor"] for r in first[str(pos)]]
        need(len(sites) <= 1, "earliest observed group has multiple distinct cuts")
        strata[str(pos)] = {
            "first_different_paired_cut": sites[0] if sites else None,
            "rows": rows,
        }
    return compact | {
        "status": "REPRODUCED_L25_INPUTS",
        "family_sha256": digest,
        "provenance": r["identity"],
        "measurements": {
            k: arm[k]
            for k in (
                "raw_bytes",
                "maxima",
                "live_samples",
                "scope_wall_s",
                "native_elapsed_s",
                "monitor_sha256",
                "c118_sha256",
                "loader_sha256",
                "comparison_sha256",
                "launch_sha256",
            )
        },
        "family_wall_s": r["wall_s"],
        "paired_positions": strata,
        "additional_payloads_without_gold": len(actual["without_gold"]),
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("family", "integrated-family", "archived-family", "c270-dir", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--family-sha256", required=True)
    a = cli.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        receipt = reopen(
            a.family, a.family_sha256, a.integrated_family, a.archived_family, a.c270_dir
        )
    except Exception as exc:
        receipt = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    print(receipt["status"])
    raise SystemExit(int(receipt["status"] == "FAIL_PRESERVED"))
