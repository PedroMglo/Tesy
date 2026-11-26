#!/usr/bin/env python3
"""Read-only replay of the C322 cost screen; publish only a new aggregate receipt."""

import argparse
import importlib.util
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parents[2]
CAMPAIGN = Path("results/c322-staging-inflight-fallback-20261009")
FIXTURE = "results/c276-post-c274-r2-causal-qualification-20261005T204839Z/development-inputs.json"
GATE = "tools/c322_staging_fallback_gate.py"
GATE_HASH = "2f27d12f99a97ec150e21e6c04232a81e48a47ace53c454dfd7fb7d7c252fdd9"
PINS = {
    "protocol.json": "f96ec8547ff60d8d5ef18af2d263e2b62a5e00ab46f329bcbbbae699ddfd96d5",
    "analysis.json": "f6bc35a5e00d96314152f635743349fba2606602b30877d9ce27be22860f1ec6",
    "raw-manifest.json": "5baf5e867e8ee6ab04979da25154ee958f0870289cf969fbb3cee325c1f3c34b",
    "family-receipt.json": "c2523871a0a1f51eab3379684f2e1dcd6297db09782c9d78da887435c7e3560b",
    "prepare-receipt.json": "196cc9258dee46c8f6d0f60618c93c2192641a718aae9d1065765c6349097498",
}
PAIRS = {"code153": ((0, 1), (3, 2)), "nominal153": ((5, 4), (6, 7))}
CLOCKS = ("decode32_s", "decode_forward_s", "prefill153_s", "total_s")


class Mismatch(ValueError):
    """Short diagnostic safe to publish."""


def require(test, label):
    if not test:
        raise Mismatch(label)


def confined(root, name):
    path = root / name
    require(path.resolve() == path and path.is_relative_to(root), "path outside scientific tree")
    return path


def digest(path):
    with path.open("rb") as stream:
        result = sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def verified_json(path, expected):
    data = path.read_bytes()
    require(sha256(data).hexdigest() == expected, path.name + " digest mismatch")
    return json.loads(data)


def verify_raw(root, index):
    expected = {row["path"]: row for row in index["files"]}
    require(len(expected) == len(index["files"]) == index["file_count"], "duplicate manifest entry")
    actual = set()
    size = 0
    for path in root.rglob("*"):
        require(not path.is_symlink(), "raw symlink")
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        require(path.is_file() and name in expected, "unexpected raw entry")
        row = expected[name]
        require(
            path.stat().st_size == row["bytes"] and digest(path) == row["sha256"],
            "raw size or digest mismatch",
        )
        size += row["bytes"]
        actual.add(name)
    if missing := expected.keys() - actual:
        raise FileNotFoundError(f"{len(missing)} raw entries missing")
    require(size == index["total_bytes"], "raw byte conservation")
    return {"files_verified": len(actual), "bytes_verified": size}


def replay(checkout):
    campaign = confined(checkout, CAMPAIGN)
    documents = {name: verified_json(confined(campaign, name), pin) for name, pin in PINS.items()}
    index = verify_raw(confined(campaign, "raw"), documents["raw-manifest.json"])
    protocol = documents["protocol.json"]
    previous = documents["analysis.json"]
    family = documents["family-receipt.json"]
    require(
        previous["protocol_sha256"]
        == family["protocol_sha256"]
        == documents["prepare-receipt.json"]["protocol_sha256"]
        == PINS["protocol.json"],
        "protocol lineage",
    )
    require(previous["raw_manifest_sha256"] == PINS["raw-manifest.json"], "manifest lineage")
    require(
        family["status"] == "ALL_ARMS_COMPLETE"
        and len(family["runs"]) == 8
        and all(x["returncode"] == 0 for x in family["runs"]),
        "incomplete physical family",
    )
    fixture = verified_json(confined(HERE, FIXTURE), protocol["screen_identity"]["fixture_sha256"])
    gate_path = confined(checkout, GATE)
    require(digest(gate_path) == previous["analysis_gate_sha256"] == GATE_HASH, "evaluator digest")

    # The pinned historical evaluator is read-only at arm level. Use its dependencies from main.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE / "tools"))
    spec = importlib.util.spec_from_file_location("c322_replay_gate", gate_path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.validate_resource_protocol(protocol)
    arms = [gate.arm_metrics(campaign, protocol, run, fixture) for run in protocol["runs"]]
    require(len(arms) == 8 and arms == previous["arms"], "eight arm receipts diverged")

    results = {}
    passes = []
    for case, indices in PAIRS.items():
        pairs = []
        for bi, ci in indices:
            baseline, candidate = arms[bi], arms[ci]
            require(
                baseline["case"] == candidate["case"] == case
                and (baseline["treatment"], candidate["treatment"]) == ("baseline", "candidate"),
                "frozen pair identity",
            )
            b, c = baseline["native_metrics"], candidate["native_metrics"]
            require(
                gate.initial_identity(b) == gate.initial_identity(c)
                and b["native_argmax_ids"] == c["native_argmax_ids"],
                "paired state or IDs",
            )
            pairs.append(
                {
                    "baseline_arm": bi + 1,
                    "candidate_arm": ci + 1,
                    "baseline_s": {k: b[k] for k in CLOCKS},
                    "candidate_s": {k: c[k] for k in CLOCKS},
                    "gain_percent": {k: 100 * (b[k] - c[k]) / b[k] for k in CLOCKS},
                    "baseline_waits": baseline["gate"]["stage_stats"]["waits"],
                    "candidate_waits": candidate["gate"]["stage_stats"]["waits"],
                    "candidate_expired_running": candidate["gate"]["stage_stats"][
                        "expired_running"
                    ],
                    "baseline_proc_read_bytes": baseline["process_read_bytes_accounted"],
                    "candidate_proc_read_bytes": candidate["process_read_bytes_accounted"],
                }
            )
        medians = {k: median(p["gain_percent"][k] for p in pairs) for k in CLOCKS}
        require(
            medians == previous["cases"][case]["median_gain_percent"], "paired clock divergence"
        )
        passes.append(
            all(p["gain_percent"]["decode32_s"] > 0 for p in pairs)
            and medians["decode32_s"] >= 3
            and medians["total_s"] >= 0
        )
        results[case] = {
            "pairs": pairs,
            "median_gain_percent": medians,
            "full33_logits_sha256": protocol["expected_full_logits_sha256"][case],
        }
    decision = (
        "PASS_SCREEN_CONTINUE_TO_CONFIRMATION"
        if all(passes)
        else "STOP_CANDIDATE_HARM_OR_GATE_MISS"
    )
    require(decision == previous["status"], "frozen gate decision divergence")
    return {
        "schema": "tesy-fallback-cost-audit-v1",
        "evidence": "REPRODUZIDO",
        "physical_campaign": protocol["campaign_id"],
        "decision": decision,
        "input_sha256": PINS,
        "evaluator_sha256": GATE_HASH,
        "cases": results,
        **index,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    out = args.new_output_dir.resolve()
    if out.is_relative_to(checkout):
        parser.error("output must be outside the archived checkout")
    out.mkdir(exist_ok=False)
    try:
        result = replay(checkout)
    except FileNotFoundError:
        result = {"status": "NOT_RUN_RAW_REQUIRED", "reason": "archived inputs incomplete"}
    except Exception as exc:
        result = {
            "status": "FAIL",
            "reason": str(exc) if isinstance(exc, Mismatch) else type(exc).__name__,
        }
    temp = out / ".receipt.pending"
    with temp.open("x") as stream:
        json.dump(result, stream, allow_nan=False, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(temp, out / "receipt.json")
    print(result.get("status", result.get("decision")))
    return int("status" in result)


if __name__ == "__main__":
    sys.exit(main())
