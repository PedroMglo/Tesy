"""Price a prefill-only improvement on the two supplied-work ABBA pairs of each C293 case."""

import argparse
import hashlib
import json
import math
import sys
from fractions import Fraction
from pathlib import Path
from runpy import run_path
from statistics import mean

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAMILY = ROOT / "results/c293-integrated-expert-store-native-cost-20261006"
CASES = ("nominal153", "code153")
METRICS = ("prefix_s", "prefill153_s", "decode32_s", "total_s")
PPM = 1_000_000
PINS = {
    "compact.json": "c0d2325728c356cf2788b55429761c029c104d031c58c42ed6931ccfebe41e22",
    "paired-analysis.json": "9b6d50e4916598bba0d1e11a9fc72ae70aaebf0a27f9c34cd608be6e4b1e9a93",
    "raw-manifest.json": "1fe7091ba80f028502602220d3d5b4feb6a63ec9356a0f215558fb7771213c85",
}
EVALUATOR = "906709a2022dbf5e913245ddfe68c575fa84d11f4c17df2e34219d9f11323b2c"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def pairs(rows):
    return [(rows[0], rows[1]), (rows[3], rows[2])]


def threshold(rows):
    """A common fraction in B removes B_prefill*x from the inclusive total of each pair."""

    def gains(ppm):
        return [
            1 - (b["total_s"] - b["prefill153_s"] * Fraction(ppm, PPM)) / a["total_s"]
            for a, b in pairs(rows)
        ]

    def fits(ppm):
        values = gains(ppm)
        return min(values) > 0 and mean(values) >= Fraction(8, 100)

    low, high = -1, PPM
    need(fits(high), "even a free prefill fails the total gate")
    while high - low > 1:
        mid = (low + high) // 2
        if fits(mid):
            high = mid
        else:
            low = mid
    return high, [float(100 * x) for x in gains(high)]


def archive_inputs(raw, arms):
    base = FAMILY.relative_to(ROOT) / "raw"
    manifest = {Path(row["path"]): row for row in read(FAMILY / "raw-manifest.json")["files"]}
    cases = {c: [] for c in CASES}
    for arm in arms:
        area = Path(arm["id"] + ".native")
        for fname in ("result.json", "initial.json", "all33.logits.f32"):
            p = raw / area / fname
            entry = manifest[base / area / fname]
            need(
                not p.is_symlink()
                and p.stat().st_size == entry["bytes"]
                and digest(p) == entry["sha256"],
                "native " + str(area / fname),
            )
            if fname == "all33.logits.f32":
                need(entry["sha256"] == arm["full33_logits_sha256"], "original logits")
        source = read(raw / area / "result.json")
        need(source["initial"] == read(raw / area / "initial.json"), "initial snapshot")
        need(
            all(source[k] == v for k, v in arm["metrics"].items())
            and source["transport"] == arm["transport"]
            and source["case"] == arm["case"]
            and source["profile"] == "R0"
            and source["external_prefill_calls"][-1] == 153
            and source["numerical_FFN_tiles"] == [32, 32, 32, 32, 25]
            and source["decode_calls"] == 32
            and len(source["teacher_forced_ids"]) == 32
            and source["output_rows"] == 33,
            "original work",
        )
        cases[arm["case"]].append(source)
    return cases


def composed(cases, case, ppm):
    adjusted = dict(cases)
    adjusted[case] = []
    for i, arm in enumerate(cases[case]):
        row = dict(arm)
        if i in (1, 2):
            saved = row["prefill153_s"] * ppm / PPM
            row["prefill153_s"] -= saved
            row["total_s"] -= saved
        adjusted[case].append(row)
    return adjusted


def run(raw):
    need(all(digest(FAMILY / k) == v for k, v in PINS.items()), "published authority")
    data = read(FAMILY / "compact.json")
    published = read(FAMILY / "paired-analysis.json")
    exact = {c: [] for c in CASES}
    arms = []
    for a in data["arms"]:
        file = FAMILY / (a["id"] + "-analysis.json")
        analysis = read(file)
        m = a["metrics"]
        need(
            a["measurement_valid"]
            and analysis["metrics"] == m
            and analysis["full_logits_sha256"] == a["full33_logits_sha256"]
            and analysis["case"] == a["case"]
            and analysis["transport"] == a["transport"]
            and math.isclose(
                m["prefill153_s"] + m["decode32_s"], m["total_s"], abs_tol=1e-8, rel_tol=0
            ),
            "closed C293 arm",
        )
        exact[a["case"]].append({k: Fraction(str(m[k])) for k in METRICS})
        arms.append(dict(id=a["id"], **m, receipt_sha256=digest(file)))
    cases = archive_inputs(raw, data["arms"]) if raw else None
    program = ROOT / "tools/expert_store_cost_gate.py"
    need(digest(program) == EVALUATOR, "original evaluator")
    if cases:
        sys.path.insert(0, str(program.parent))
        try:
            evaluate = run_path(program)["evaluate"]
        finally:
            sys.path.pop(0)
        base = evaluate(cases)
        need(all(base[k] == published[k] for k in base), "original evaluator reproduction")
    result = {}
    for case, other in ((CASES[0], CASES[1]), (CASES[1], CASES[0])):
        rows = exact[case]
        need(len(rows) == 4, "four native arms")
        for (a, b), old in zip(pairs(rows), published["cases"][case]["pairs"], strict=True):
            need(
                all(
                    abs(float(100 * (1 - b[k] / a[k])) - old["gain_percent"][k]) < 1e-9
                    for k in METRICS
                ),
                "paired original",
            )
        ppm, gains = threshold(rows)
        guard = published["cases"][other]["median_paired_gain_percent"]["total_s"]
        need(guard >= -5 and ppm > 0, "untouched other case and positive new intervention")
        price = dict(
            minimum_prefill_ppm=ppm,
            seconds_by_candidate_pair=[
                float(b["prefill153_s"] * ppm / PPM) for a, b in pairs(rows)
            ],
            paired_total_gain_percent=gains,
            other_case_total_gain_percent=guard,
        )
        if cases:
            before = evaluate(composed(cases, case, ppm - 1))
            at = evaluate(composed(cases, case, ppm))
            need(
                case not in before["global_qualified_cases"]
                and case in at["global_qualified_cases"],
                "official threshold",
            )
            price.update(
                official_status_before=before["status"],
                official_status_at=at["status"],
                phase_survivors_at=at["phase_survivor"],
            )
        result[case] = price
    return dict(
        classification="CONDITIONAL_SUPPLIED_WORK_BUDGET",
        inputs=PINS,
        assessor_sha256=EVALUATOR,
        protocol_sha256=digest(HERE / "composition.md"),
        raw_reopened=bool(raw),
        arms=arms,
        cases=result,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir()
    try:
        receipt = run(a.raw_dir)
    except (ValueError, OSError, KeyError) as exc:
        receipt = dict(classification="FAIL_PRESERVED", reason=str(exc))
    with (a.new_output_dir / "composition.json").open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(receipt["classification"], receipt.get("reason", ""))
    raise SystemExit(int(receipt["classification"] == "FAIL_PRESERVED"))
