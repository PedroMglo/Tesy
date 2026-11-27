"""A necessary capacity bound and a single explicit hindsight witness for both observations."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(str(HERE / "residency.py"))
BASE, SRC, require = (R[k] for k in ("BASE", "SRC", "require"))
METHOD = "8f39be094a44fee94fda0348108ab5d89616fc47fc5e358d0d863ee62fd5d8d5"
SELECTION = "250aa33f58ce1060edb73f3336e78861a2d70c73ff21fe2f4fb9248eafed9d96"


def supporting_credit(calls, groups):
    credits = {"first_final": Counter(), "decode": Counter()}
    for call in calls:
        scores = Counter()
        total = 0
        for jobs in groups[call.number].values():
            costs = [j.read_ns + j.set_ns for j in jobs]
            total += BASE["layer_fourths"](costs)
            biggest = max(costs)
            if 4 * biggest >= sum(costs):
                j = min(
                    (j for j, c in zip(jobs, costs, strict=True) if c == biggest),
                    key=lambda j: (j.expert, j.read_ns),
                )
                scores[j.expert] += 4 * j.read_ns
            else:
                for j in jobs:
                    scores[j.expert] += j.read_ns
        if total > 4 * (call.span - call.remap):
            if call.number <= 46:
                credits["first_final"].update(scores)
            if call.number >= 3:
                credits["decode"].update(scores)
    return credits


def upper_ns(scores, offered, cap, eligible_calls):
    top = sorted((scores[k] for k in offered), reverse=True)[:cap]
    return (sum(top) + 3) // 4 + eligible_calls


def run(archive):
    require(SRC["digest"](HERE / "existence-protocol.md") == METHOD, "protocol hash")
    causal = SRC["pinned"](HERE / "selection-result.json", SELECTION)
    prior = SRC["pinned"](
        BASE["NATURAL"] / "prefill_retention/request_cost/receipt.json", BASE["PRIOR"]
    )
    models, scores, results = {}, {}, {}
    offered = set()
    lineage = None
    for label in ("P106", "P97"):
        name, family, _ = SRC["SOURCES"][label]
        root = archive / ("part-" + label[1:]) / name
        (calls, _, _), auth = BASE["read_arm"](archive, label, prior[label])
        if label == "P106":
            sealed, rows, tiers, _ = SRC["Q"]["read_new"](root, family)
            offered = set(map(tuple, sealed["offered_keys"]))
        else:
            rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
            receipt = json.loads((root / "ON/receipt.json").read_bytes())
            log = root / "ON/raw" / receipt["native_ids"]["raw_stderr_file"]
            tiers, _ = SRC["T"]["mapping"](log.read_bytes(), rows)
        groups, _, origins = R["raw_groups"](rows, tiers)
        identity = (origins, SRC["Q"]["bindings"](rows), auth["trajectory_sha256"])
        require(lineage is None or identity == lineage, "different route/lineage")
        lineage = identity
        model = calls, groups, auth["outside_calls_ns"]
        empty = R["bounds"](*model)
        require(
            all(empty[k] == auth["clock_ns"]["ready"][k] for k in ("first_final", "decode")),
            "empty oracle ablation",
        )
        credits = supporting_credit(calls, groups)
        count = {
            "first_final": sum(c.number <= 46 for c in calls),
            "decode": sum(c.number >= 3 for c in calls),
        }
        upper = {k: upper_ns(v, offered, R["BUDGET"], count[k]) for k, v in credits.items()}
        results[label] = {
            "upper_gain_ns": upper,
            "empty": {k: empty[k] for k in upper},
            "exclusion": any(empty["margin_ns"][k] + upper[k] < 0 for k in upper),
        }
        models[label] = model
        scores[label] = credits
    require(len(offered) == 2829, "T1 offer universe")
    keys = sorted(
        offered,
        key=lambda k: (-scores["P106"]["first_final"][k], -scores["P97"]["first_final"][k], k),
    )[: R["BUDGET"]]
    bank = set(keys)
    require(len(bank) == R["BUDGET"], "capacity witness")
    for label, model in models.items():
        candidate = R["bounds"](*model, bank=bank)
        entry = results[label]
        for k, upper in entry["upper_gain_ns"].items():
            require(0 <= entry["empty"][k] - candidate[k] <= upper, "witness exceeds upper bound")
        entry["witness"] = candidate
        entry["first_gain_over_causal_ns"] = (
            causal["arms"][label]["copied"]["first_final"] - candidate["first_final"]
        )
    margin = min(BASE["joint"](v["witness"]) for v in results.values())
    excluded = any(v["exclusion"] for v in results.values())
    require(not (excluded and margin >= 0), "exclusion contradicts constructive bank")
    status = (
        "EXISTS_HEADROOM_ONLY"
        if margin >= 0
        else ("NO_GO_ALL_BANKS" if excluded else "INCONCLUSIVE")
    )
    digest = hashlib.sha256(json.dumps(sorted(bank), separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "tesy.expert_ready_hindsight.v1",
        "status": "TRACE_DERIVED",
        "decision": status,
        "protocol_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "selection_receipt_sha256": SELECTION,
        "offered": len(offered),
        "capacity": len(bank),
        "one_acquisition_per_selected_key_bytes": len(bank) * R["PAYLOAD"],
        "witness_keys_sha256": digest,
        "common_joint_margin_ns": margin,
        "arms": results,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    a = cli.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve() if exc.filename else None
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing and missing.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing_file": missing.name if missing else None,
        }
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    tmp = a.new_output_dir / ".pending"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(result["status"], result.get("decision", result.get("reason", "")))
    return int(result["status"] != "TRACE_DERIVED")


if __name__ == "__main__":
    raise SystemExit(main())
