"""Price all three previously frozen T1-only selectors, granting free hit SET and all pre-stream time."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CC = run_path(HERE / "client_cost.py")
B, C, SRC, need = (CC[k] for k in ("B", "C", "SRC", "need"))


def run(archive):
    material = SRC["pinned"](HERE.parent / "selection-result.json", C["E"]["SELECTION"])
    name, family, _ = SRC["SOURCES"]["P106"]
    root = archive / "part-106" / name
    # Each plan is bound to T1 before it is allowed to see the T2 group prices.
    plan = run_path(HERE.parent / "selection.py")["train"](root / "ON")
    seal, _, _, _ = SRC["Q"]["read_new"](root, family)
    keys = {k: v["ordered_keys"] for k, v in seal["banks"].items()}
    need(
        set(keys) == {"lru", "prefill"}
        and plan["keys_sha256"] == material["selection"]["keys_sha256"],
        "causal plans",
    )
    keys["publication"] = plan["keys"]
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    need(prior["P106"]["pre_stream_allowance_ns"] == CC["CREDIT"], "client interval")
    data = {}
    for label in ("P106", "P97"):
        regs, auth, _, _ = C["load_arm"](archive, label, prior[label])
        data[label] = (regs, auth["outside_calls_ns"])
    result = {}
    for label, values in keys.items():
        bank = set(map(tuple, values))
        need(len(bank) == len(values) == 353, "causal population")
        entry = CC["assess"](data, bank, True)
        entry["keys_sha256"] = hashlib.sha256(
            json.dumps(sorted(bank), separators=(",", ":")).encode()
        ).hexdigest()
        result[label] = entry
    return {
        "schema": "tesy.ready_t1_controls.v1",
        "status": "TRACE_DERIVED",
        "credit_ns": CC["CREDIT"],
        "source_sha256": SRC["digest"](Path(__file__)),
        "results": result,
        "decisions": {
            k: "HEADROOM_ONLY" if v["fits_with_grant"] else "NO_GO" for k, v in result.items()
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(a.archive)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve()
        report = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing.is_relative_to(a.archive.resolve())
            else "FAIL",
            "missing": missing.name,
        }
    except (ValueError, OSError, KeyError, AssertionError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    raise SystemExit(report["status"] != "TRACE_DERIVED")
