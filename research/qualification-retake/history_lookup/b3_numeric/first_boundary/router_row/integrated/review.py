"""Reopen the raw integrated pair and its original controls without resident model or target."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import binding  # noqa: E402
import evaluate  # noqa: E402

need, read, sha = evaluate.need, evaluate.read, evaluate.sha


def reopen(a):
    family = a.family
    need(sha(family / "receipt.json") == a.family_sha256, "terminal identity")
    r = read(family / "receipt.json")
    need(
        r["status"] in ("RESTORED_86_AND_FULL_OUTPUTS", "DIFFERENT_AT_OBSERVED_CUT_OR_OUTPUT")
        and r["model_launch_receipts"] == 2
        and set(r["arms"]) == {"OFF", "ON"},
        "complete pair",
    )
    origins = evaluate.reference(a.archived_family)
    evaluate.boundary.historical(a.original_family)
    later = evaluate.later_reference(a.c270_dir)
    historical_coverage = evaluate.boundary.old_rows()
    result = {}
    for mode, reference in (("OFF", "B3"), ("ON", "AR")):
        folder = family / mode
        need(sha(folder / "receipt.json") == r["arms"][mode]["receipt_sha256"], "arm receipt")
        arm = read(folder / "receipt.json")
        unit = arm["unit"]
        need(
            arm["status"] == "OBSERVED_" + mode
            and Path(unit).name == unit
            and arm["model_launch_receipts"] == 1,
            "measured arm status",
        )
        raw = folder / "raw"
        cap = raw / (unit + ".capture")
        files = {
            raw / (unit + ".start-inventory.jsonl"): "c118_sha256",
            raw / (unit + ".json"): "monitor_sha256",
            raw / (unit + ".launch.json"): "launch_sha256",
            folder / "loader-audit.json": "loader_sha256",
            folder / "comparison.json": "comparison_sha256",
            folder / "command.json": "command_sha256",
            folder / "integrated-resource.json": "resource_sha256",
        }
        need(all(sha(k) == arm[v] for k, v in files.items()), "arm receipt witness")
        observation = evaluate.compare(cap, mode, origins[reference], later, binding.OLD)
        need(
            observation == read(folder / "comparison.json")
            and observation["bitwise"] == arm["bitwise"],
            "independent exact comparison",
        )
        prefix = binding.OLD.check_prefix(cap, origins[reference])
        need(
            prefix == arm["grade"]["prefix"] == historical_coverage[reference]["prefix"],
            "all prefill witnesses",
        )
        states = arm["grade"]["states"]
        need(
            all(
                sha(cap / n) == v["sha256"] and (cap / n).stat().st_size == v["bytes"]
                for n, v in states.items()
            ),
            "stored KV/pool witnesses",
        )
        record = {
            k: arm[k]
            for k in (
                "library_sha256",
                "client_sha256",
                "raw_bytes",
                "live_samples",
                "scope_wall_s",
                "native_elapsed_s",
                "maxima",
                "monitor_sha256",
                "c118_sha256",
                "launch_sha256",
                "loader_sha256",
                "comparison_sha256",
            )
        }
        late = {}
        for row in observation["comparisons"]:
            if not 6 <= row["group"] <= 9:
                continue
            kind = late.setdefault(
                row["site"],
                {"different_rows": 0, "different_words": 0, "words": 0, "rows": 0, "layers": []},
            )
            kind["rows"] += 1
            kind["words"] += row["words"]
            kind["different_rows"] += int(bool(row["changed_words"]))
            kind["different_words"] += row["changed_words"]
            if row["changed_words"] and row["layer"] not in kind["layers"]:
                kind["layers"].append(row["layer"])
        result[mode] = (
            record
            | {
                k: observation[k]
                for k in (
                    "bitwise",
                    "routers_equal",
                    "routers_with_gold",
                    "first",
                    "states",
                    "logits",
                    "observed_router_rows",
                    "common_equal",
                    "common_payloads",
                )
            }
            | {
                "cut_bytes": observation["coverage"]["bytes"],
                "cut_payloads": observation["coverage"]["payloads"],
                "router_stages": late,
                "familial_receipt_sha256": sha(folder / "receipt.json"),
                "prefix": prefix,
            }
        )
    need(
        result["OFF"]["bitwise"]
        and (r["status"] == "RESTORED_86_AND_FULL_OUTPUTS") == result["ON"]["bitwise"],
        "pair decision",
    )
    return {
        "status": "REPRODUCED_" + r["status"],
        "arms": result,
        "family_sha256": a.family_sha256,
        "measurement_commit": r["measurement_commit"],
        "build_sha256": r["build_sha256"],
        "window_sha256": r["c55_sha256"],
        "protocol_sha256": r["protocol_sha256"],
        "original_family_sha256": r["original_family_sha256"],
        "historical_family_sha256": r["historical_family_sha256"],
        "family_wall_s": r["wall_s"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for label in ("family", "archived-family", "original-family", "c270-dir", "new-output-dir"):
        p.add_argument("--" + label, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        rec = reopen(a)
    except Exception as exc:
        rec = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    (a.new_output_dir / "receipt.json").write_text(json.dumps(rec, sort_keys=True, indent=2) + "\n")
    print(rec["status"])
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))
