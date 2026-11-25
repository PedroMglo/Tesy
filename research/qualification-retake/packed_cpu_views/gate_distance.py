"""Distance from actual C293 pairs to the historical 8% total-time criterion."""

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "results/c293-integrated-expert-store-native-cost-20261006"
sys.path.insert(0, str(ROOT / "tools"))
import expert_store_cost_gate as historical  # noqa: E402

MANIFEST = "1fe7091ba80f028502602220d3d5b4feb6a63ec9356a0f215558fb7771213c85"
ANALYSIS = "9b6d50e4916598bba0d1e11a9fc72ae70aaebf0a27f9c34cd608be6e4b1e9a93"
COMPACT = "c0d2325728c356cf2788b55429761c029c104d031c58c42ed6931ccfebe41e22"


def check(value, label):
    if not value:
        raise ValueError(label)


def pinned(path, digest, size=None):
    data = path.read_bytes()
    check(size is None or len(data) == size, "length: " + path.name)
    check(hashlib.sha256(data).hexdigest() == digest, "identity: " + path.name)
    return json.loads(data)


def counterfactual(cases, case, cuts, factor):
    changed = {k: list(v) for k, v in cases.items()}
    for idx, cut in zip((1, 2), cuts, strict=True):
        b = dict(cases[case][idx])
        # Attribute this hypothetical saving proportionately to the
        # two phases solely to exercise the complete evaluator.
        keep = 1 - (cut * factor) / b["total_s"]
        for k in ("prefill153_s", "decode32_s", "total_s"):
            b[k] *= keep
        changed[case][idx] = b
    return historical.evaluate(changed)


def study(raw):
    arms = pinned(SOURCE / "compact.json", COMPACT)["arms"]
    old = pinned(SOURCE / "paired-analysis.json", ANALYSIS)
    entries = {
        x["path"].split("/raw/")[-1]: x
        for x in pinned(SOURCE / "raw-manifest.json", MANIFEST)["files"]
    }
    cases = {case: [] for case in ("nominal153", "code153")}
    for arm in arms:
        name = arm["id"] + ".native/result.json"
        data = pinned(raw / name, entries[name]["sha256"], entries[name]["bytes"])
        case = data["case"]
        check(
            all(data[k] == v for k, v in arm["metrics"].items())
            and historical.loads(data) == arm["logical_load_generations"]
            and arm["measurement_valid"]
            and arm["full33_logits_sha256"] == old["full33_logits_sha256"][case][len(cases[case])],
            "native metrics, generations or numerical receipt",
        )
        historical.transport(data, arm["transport"])
        cases[case].append(data)
    original = historical.evaluate(cases)
    check(all(old[k] == v for k, v in original.items()), "historical evaluator mismatch")
    out = {}
    for case, rows in cases.items():
        pairs = [(rows[0], rows[1]), (rows[3], rows[2])]
        gap = 8.0 - original["cases"][case]["median_paired_gain_percent"]["total_s"]
        check(gap > 0, "already qualified")
        # For equal absolute time saved in both B arms, the change in the
        # median of two paired gains is the arithmetic mean of 100*dt/A.
        seconds = gap / statistics.mean(100 / a["total_s"] for a, _ in pairs)
        fraction = gap / statistics.mean(100 * b["total_s"] / a["total_s"] for a, b in pairs)
        scenarios = {}
        for kind, cuts in (
            ("equal_seconds", [seconds] * 2),
            ("equal_fraction", [fraction * b["total_s"] for _, b in pairs]),
        ):
            below, above = (
                counterfactual(cases, case, cuts, 1 - 1e-6),
                counterfactual(cases, case, cuts, 1 + 1e-6),
            )
            check(
                case not in below["global_qualified_cases"]
                and case in above["global_qualified_cases"],
                "unconfirmed threshold",
            )
            gains = [
                100 * (a["total_s"] - b["total_s"] + cut) / a["total_s"]
                for (a, b), cut in zip(pairs, cuts, strict=True)
            ]
            check(
                min(gains) > 0 and math.isclose(statistics.mean(gains), 8, abs_tol=1e-9),
                "pair signs or mean",
            )
            scenarios[kind] = dict(seconds_by_pair=cuts, gain_percent_by_pair=gains)
        out[case] = dict(
            original_pairs=original["cases"][case]["pairs"],
            median_original=original["cases"][case]["median_paired_gain_percent"],
            same_fraction_of_B=fraction,
            same_seconds_from_B=seconds,
            scenarios=scenarios,
        )
    return dict(
        status="REPRODUCED_C293_CONDITIONAL_THRESHOLD",
        source_sha256=dict(compact=COMPACT, manifest=MANIFEST, analysis=ANALYSIS),
        arms=out,
        physical_savings="UNKNOWN",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        evidence = study(args.raw_dir)
    except (OSError, KeyError, ValueError, IndexError) as exc:
        evidence = dict(status="FAIL_PRESERVED", error=type(exc).__name__ + ": " + str(exc))
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(evidence, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(evidence["status"])
    raise SystemExit(evidence["status"] == "FAIL_PRESERVED")
