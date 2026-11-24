#!/usr/bin/env python3
"""Regrade frozen C133 and look for the same official input in local history."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Historical tools import their siblings as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import c133_diverse_session_retry as historical
from c2_gate import GateError, strict_json
from c2_server_run import digest
from run_bounded import sha256

ROOT = Path(__file__).resolve().parents[2]
C132 = "c132-diverse-active-session-20260929T1939Z"
C133 = historical.ROOT_NAME
STATUS = "FAIL_OUTPUT_CAP_INTERRUPTED_OPERATOR"
DECISIONS = {
    C132: "84f0b1eac06df6be95c39389af5def819b08d086231f8fb8841452bcaba1d9c7",
    C133: "9f52ea6f2f09f1be56ab92cc6eac785daca85e51b7cbcaa00a0f134e6160610e",
}


class EvidenceMismatch(ValueError):
    """Only use messages safe to publish without any response text."""


def check(condition, message):
    if not condition:
        raise EvidenceMismatch(message)


def read(path):
    return strict_json(path.read_text())


def checked(path, expected):
    check(sha256(path) == expected, f"SHA-256 mismatch in {path.name}")
    return read(path)


def run_id(campaign):
    return campaign[:4] + "-c75-slots40-diverse20"


def tokens_file(root, campaign):
    return root / campaign / "raw" / (run_id(campaign) + ".tokenization.json")


def token_rows(mapping):
    check(isinstance(mapping, dict) and mapping, "invalid tokenization schema")
    for key, ids in mapping.items():
        check(
            isinstance(ids, list)
            and ids
            and all(type(value) is int and value >= 0 for value in ids),
            "invalid token ID array",
        )
        yield key, ids


def scan(root, target):
    manifest, matches = [], []
    requests = 0
    for path in sorted(root.rglob("*.tokenization.json")):
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        checksum = hashlib.sha256(data).hexdigest()
        manifest.append([relative, len(data), checksum])
        for key, ids in token_rows(strict_json(data)):
            requests += 1
            if ids == target:
                matches.append(
                    {
                        "file_sha256": checksum,
                        "request_id_sha256": digest(key),
                        "known_capture": next(
                            (c[:4] for c in DECISIONS if path == tokens_file(root, c)), None
                        ),
                    }
                )
    return {
        "files": len(manifest),
        "requests": requests,
        "manifest_sha256": digest(manifest),
        "matches": matches,
    }


def recheck(root, scan_all):
    refs = ROOT / "results"
    decisions = {c: checked(refs / c / "decision.json", value) for c, value in DECISIONS.items()}
    a, b = decisions[C132], decisions[C133]
    interrupted = checked(refs / C132 / "interruption.json", a["interruption_sha256"])
    analysis = checked(refs / C133 / "analysis.json", b["analysis_sha256"])
    old_path, new_path = (tokens_file(root, c) for c in [C132, C133])
    old_digest = interrupted["raw_local_files_sha256"][old_path.name]
    old = checked(old_path, old_digest)
    new = checked(new_path, analysis["official_tokenization_sha256"])
    check(
        a["status"] == interrupted["status"] == STATUS
        and interrupted["canonical_full_responses"] == "UNAVAILABLE"
        and interrupted["raw_json"] == "NOT_WRITTEN_AFTER_KEYBOARDINTERRUPT"
        and all(
            not (old_path.parent / (run_id(C132) + suffix)).exists()
            for suffix in [".json", ".receipt.json"]
        ),
        "C132 interruption mismatch",
    )
    campaign = root / C133
    run = run_id(C133)
    protocol_name = "protocols/" + run + ".json"
    config_name = run + "-config.json"
    freeze = read(refs / C133 / "preflight.json")
    for filename, checksum in freeze["files"].items():
        check(sha256(campaign / filename) == checksum, "C133 freeze mismatch")
    protocol = read(campaign / protocol_name)
    config = read(campaign / config_name)
    check(
        sha256(historical.WORKLOAD)
        == freeze["workload_sha256"]
        == protocol["identity"]["workload_sha256"]
        and protocol["c133"]["prior_c132_decision_sha256"] == DECISIONS[C132]
        and digest(config) == protocol["identity"]["config_sha256"],
        "workload/config mismatch",
    )
    raw = checked(new_path.parent / (run + ".json"), b["raw_sha256"])
    receipt = checked(new_path.parent / (run + ".receipt.json"), b["receipt_sha256"])
    old_pre_path = old_path.parent / (run_id(C132) + ".preflight.json")
    old_pre_digest = interrupted["raw_local_files_sha256"][old_pre_path.name]
    old_pre = checked(old_pre_path, old_pre_digest)
    old_protocol = checked(
        refs / C132 / "protocols" / (run_id(C132) + ".json"), old_pre["protocol_sha256"]
    )
    check(
        old_pre["protocol"] == old_protocol
        and all(
            old_protocol["identity"][k] == protocol["identity"][k]
            for k in ["model_sha256", "backend_sha", "binary_sha256", "library_sha256"]
        )
        and old_pre["config"]["server_command"] == config["server_command"]
        and old_pre["config"]["explicit_env"] == config["explicit_env"]
        and old_pre["config"]["append_previous_assistant_to_next"]
        and config["append_previous_assistant_to_next"],
        "C132/C133 target, history or runtime identity mismatch",
    )
    inventory_sha = sha256(new_path.parent / (run + ".start-inventory.receipt.json"))
    check(
        receipt["model_launch_observed"] is True
        and receipt["measurement_commit"] == b["measurement_commit"]
        and analysis["raw_sha256"] == receipt["raw_sha256"] == b["raw_sha256"]
        and analysis["receipt_sha256"] == b["receipt_sha256"]
        and analysis["inventory_sha256"] == receipt["inventory_receipt_sha256"] == inventory_sha,
        "C133 provenance mismatch",
    )
    historical.configure()
    maxima, details, timing = historical.parent.validate(campaign, protocol, config, raw)
    check(
        receipt["results"] == details
        and receipt["maxima"] == maxima
        and receipt["timing"] == timing
        and timing["duration_pass"],
        "C133 envelope mismatch",
    )
    failures = [
        {"id": row["id"], "missing": row["grade"]["missing"]}
        for row in details
        if row["grade"]["status"] != "PASS"
    ]
    check(
        failures == analysis["content_failures"] == [{"id": "c133-turn02", "missing": ["Aster"]}]
        and len(details) == analysis["natural_finishes"] == 20
        and analysis["content_pass_count"] == len(details) - len(failures)
        and b["status"]
        == analysis["status"]
        == receipt["status"]
        == "SESSION_QUALITY_OR_DURATION_NO_GO",
        "C133 product decision mismatch",
    )
    expected_old = [f"c132-turn{i:02d}" for i in range(1, 6)]
    check(list(dict(token_rows(old))) == expected_old, "C132 captured turn set mismatch")
    list(token_rows(new))
    common = [new[key.replace("c132", "c133", 1)] == old[key] for key in expected_old]
    check(common == [True, True, True, True, False], "history comparison mismatch")
    turn = raw["results"][1]
    result = {
        "schema": "tesy-product-reference-v1",
        "status": "REPRODUZIDO",
        "product_decision": b["status"],
        "independent_target_attribution": "INCONCLUSIVE",
        "c132": {"status": STATUS, "canonical_responses": "UNAVAILABLE"},
        "sha256": {
            "decisions": DECISIONS,
            "c132_interruption": a["interruption_sha256"],
            "c133_analysis": b["analysis_sha256"],
            "raw": b["raw_sha256"],
            "receipt": b["receipt_sha256"],
            "inventory": inventory_sha,
            "c132_ids": old_digest,
            "c133_ids": analysis["official_tokenization_sha256"],
            "c132_preflight": old_pre_digest,
            "c132_protocol": old_pre["protocol_sha256"],
            "c133_workload": freeze["workload_sha256"],
            "c133_protocol": freeze["files"][protocol_name],
        },
        "history_comparison": [
            {
                "turn": i,
                "same_ids": same,
                "c132_tokens": len(old[key]),
                "c133_tokens": len(new[key.replace("c132", "c133", 1)]),
            }
            for i, (key, same) in enumerate(zip(expected_old, common, strict=True), 1)
        ],
        "c133": {
            "completed": len(details),
            "natural": analysis["natural_finishes"],
            "validator_pass": analysis["content_pass_count"],
            "failed_turns": [2],
            "duration_pass": timing["duration_pass"],
            "turn02_prompt_tokens": turn["usage"]["prompt_tokens"],
            "turn02_cached_tokens": turn["timings"]["cache_n"],
            "turn02_new_tokens": turn["timings"]["prompt_n"],
            "turn02_prompt_ids_sha256": digest(new["c133-turn02"]),
        },
        "local_tokenization_scan": scan(root, new["c133-turn02"]) if scan_all else None,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-results", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument("--scan-tokenizations", action="store_true")
    args = parser.parse_args()
    root = args.historical_results.resolve()
    out = args.new_output_dir.resolve()
    if out.is_relative_to(root):
        parser.error("use an output directory outside the historical results")
    # mkdir is the exclusive reservation, including concurrent invocations.
    out.mkdir()
    try:
        result = recheck(root, args.scan_tokenizations)
    except FileNotFoundError as exc:
        path = Path(exc.filename)
        result = {
            "status": "NOT_RUN_RAW_REQUIRED" if path.is_relative_to(root) else "FAIL",
            "missing_file": path.name,
        }
    except EvidenceMismatch as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    except (ValueError, GateError, OSError, KeyError, TypeError) as exc:
        # Decoder errors and exception details can contain private input.
        result = {"status": "FAIL", "exception_type": type(exc).__name__}
    staging = out / ".receipt.pending"
    with staging.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    staging.replace(out / "receipt.json")
    print(result["status"])
    return 0 if result["status"] == "REPRODUZIDO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
