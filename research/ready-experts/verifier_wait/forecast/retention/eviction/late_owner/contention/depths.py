"""Qualify actual peer pread clocks at every populated mixed depth in the renewable bank."""

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
X = run_path(HERE / "mixed.py")
DEV = run_path(HERE / "device.py")
V, F, C, need, sha, save = (X[k] for k in ("V", "F", "C", "need", "sha", "save"))
M, IO = (DEV[k] for k in ("M", "IO"))
METHOD = "0f5858305039757c553fd6d1c1fdce1ead45f9e433ba0a84d46ed13974c51ef1"
MIXED = "c171c3a67263c143bf1eb303f38f398eac131f12a073dbc1964192af68b12ebb"
PRELUDE = "8b01fc7cd63f5621c97766ca7f9cd3b298230f82736f4735c6ece1bcf54a0cb6"
SHAPES = [f"{q}/{k}" for q in range(2, 5) for k in range(1, q)]
PPM = V["PPM"]


def classify(rows, hits):
    cohorts = defaultdict(set)
    amounts = defaultdict(Counter)

    def collect(live, q, k, width):
        if not 0 < k < q:
            return
        misses = sorted(live - hits)
        name = f"{q}/{k}"
        for i in misses:
            amounts[i][name] += width
        if len({tuple(rows[i - 1][1][:3]) for i in live}) == 1:
            cohorts[name].add(tuple([*misses, *sorted(live & hits)]))

    credits, _ = X["split"](rows, hits, on_interval=collect)
    need(
        {i: sum(c.values()) for i, c in amounts.items()} == credits["simultaneous"],
        "interval accounting",
    )
    return cohorts, amounts


def inputs():
    tx, effect = V["sources"]()
    hits = {i for i, e in enumerate(effect, 1) if e[1] is not None}
    raw = F["unpack"](X["ORIGINAL"] / "service.json.gz")
    need(sha(X["ORIGINAL"] / "service.json.gz") == V["SERVICE"], "authenticated service")
    common = None
    by_arm = {}
    for tag, data in raw.items():
        rows = data["jobs"]
        need(
            all(
                r[0] == [layer, sl, gen, e]
                for r, (_, _, layer, sl, gen, e, _) in zip(rows, tx, strict=True)
            ),
            "route ordinals",
        )
        candidates, by_arm[tag] = classify(rows, hits)
        common = {
            s: candidates[s] if common is None else (candidates[s] & common[s]) for s in SHAPES
        }
    groups = {}
    for shape in SHAPES:
        count = len(common[shape])
        if count:
            ords = min(common[shape])
            groups[shape] = dict(
                common=count,
                ordinals=list(ords),
                keys=[128 * tx[i - 1][2] + tx[i - 1][5] for i in ords],
            )
    return groups, by_arm, hits


def plan(a):
    old = M["verified"](a.mixed, MIXED)
    need(
        old["method"] == X["METHOD"]
        and old["joint"]["favorable"]["simultaneous"]["full_margin_ns"] >= 0,
        "physical gate",
    )
    groups, _, _ = inputs()
    ref = M["verified"](a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    idx = M["verified"](a.manifest / "integral-index.json", ref["index_sha256"])
    experts = {128 * e["layer"] + e["expert"]: e for e in idx["experts"]}
    need(len(experts) == 4608 and idx["weight_window"] == DEV["SIZE"], "index")
    st = [ref["pack_stat"][k] for k in M["STAT"]]
    dest = a.new_output_dir / "windows.tsv"
    expected = 0
    with dest.open("x") as f:
        print(*st, len(groups), file=f)
        for label, g in groups.items():
            q, k = map(int, label.split("/"))
            need(len(g["keys"]) == len(set(g["keys"])) == q, "capacity or duplicate")
            expected += 121 * q - 60 * k
            print(q, k, file=f)
            for key in g["keys"]:
                e = experts[key]
                ms = e["components"][:3]
                need(
                    [v["packed_relative_offset"] for v in ms] == [0, DEV["SLAB"], 2 * DEV["SLAB"]]
                    and all(v["size_bytes"] == DEV["SLAB"] and v["type"] == "mxfp4" for v in ms),
                    "components",
                )
                print(e["pack_offset"], *(v["sha256"] for v in ms), file=f)
    return dict(
        labels=list(groups),
        groups=groups,
        expected_records=expected,
        windows=sha(dest),
        pack_path=ref["pack_path"],
        model_path=ref["model_path"],
        pack_stat=st,
        model_stat=[ref["model_stat"][k] for k in M["STAT"]],
        model=ref["model_sha256"],
        pack=ref["pack_sha256"],
        index=ref["index_sha256"],
        manifest=M["PREP"]["MANIFEST"],
    )


def build(a):
    hist = HERE / "peer.cpp"
    need(sha(hist) == PRELUDE, "fixed reader ABI")
    header, sep, _ = hist.read_text().partition("struct Trial {")
    need(bool(sep), "native boundary")
    path = a.new_output_dir / "mixed.cpp"
    with path.open("x") as f:
        f.write(header + (HERE / "mixed.cpp.in").read_text())
    return DEV["build"](a, reader_source=path)


def schedule():
    for stage in range(4):
        for order, p in [(-1, 0), *((o, p) for o in (0, 1) for p in range(1, 8))]:
            for leg in range(2):
                alt = int((order == 1) != bool(leg))
                yield (
                    stage,
                    order,
                    p,
                    (stage if stage < 2 else alt),
                    (alt if stage < 2 else int(stage == 3)),
                )


def ratio_value(x):
    return [x.numerator, x.denominator]


def grade_class(data, misses):
    calibration = []
    rates = []
    off = []
    for order in (0, 1):
        for stage in (0, 1):
            pairs = [data[stage, order, i] for i in range(1, 8)]
            r = median(Fraction(b[1][0], b[0][0]) for b in pairs)
            calibration.append(r)
        pairs = [data[2, order, i] for i in range(1, 8)]
        off.append([median(b[1][col] - b[0][col] for b in pairs) for col in range(3)])
        pairs = [data[3, order, i] for i in range(1, 8)]
        for w in range(misses):
            j = 3 + 2 * w
            d = [v[0][j + 1] - v[0][j] for v in pairs]
            h = [v[1][j + 1] - v[1][j] for v in pairs]
            rates.append(median(Fraction(a - b, a) for a, b in zip(d, h, strict=True)))
    valid = all(Fraction(97, 100) <= r <= Fraction(103, 100) for r in calibration)
    lower = max(0, min(PPM, math.floor(min(rates) * PPM)))
    upper = max(0, min(PPM, math.ceil(max(rates) * PPM)))
    return dict(
        neutral=valid,
        median_ON_over_OFF=list(map(ratio_value, calibration)),
        OFF_H_minus_D_ns=off,
        median_lane_reduction=list(map(ratio_value, rates)),
        reduction_ppm=[lower, upper] if valid else [0, PPM],
    )


def parse(lines, plan):
    labels = plan["labels"]
    need(
        labels == [s for s in SHAPES if s in labels]
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained"
        and len(lines) == 2 + 121 * len(labels),
        "receipt shape",
    )
    classes = {}
    records = hashes = 0
    for idx, label in enumerate(labels):
        q, k = map(int, label.split("/"))
        data = defaultdict(dict)
        for row, spec in enumerate(schedule()):
            tag, *tail = lines[1 + 121 * idx + row].split()
            fields = list(map(int, tail))
            need(
                tag == "row" and len(fields) == 17 and fields[:6] == [idx, *spec], "trial identity"
            )
            stage, order, p, hit, trace = spec
            peers, reads, drain, *marks = fields[6:]
            need(0 < peers <= reads <= drain, "clock gates")
            for w in range(4):
                a, b = marks[2 * w : 2 * w + 2]
                issued = w < q and (not hit or w < q - k)
                need(
                    0 <= a < b <= (peers if w < q - k else reads)
                    if issued and trace
                    else a == b == 0,
                    "READ interval",
                )
            bank = data[stage, order, p]
            key = trace if stage < 2 else hit
            need(key not in bank, "repeated leg")
            bank[key] = fields[6:]
        tag, *tail = lines[121 * (idx + 1)].split()
        got = list(map(int, tail))
        issued = [121] * (q - k) + [61] * k + [0] * (4 - q)
        checks = [363] * q + [0] * (4 - q)
        need(tag == "closed" and got == [idx, *issued, *checks], "read and hash conservation")
        classes[label] = grade_class(data, q - k)
        records += sum(issued)
        hashes += sum(checks)
    need(records == plan["expected_records"], "requested volume")
    return dict(
        classes=classes,
        requested_records=records,
        hashes=hashes,
        trials=120 * len(labels),
        model_forwards=0,
    )


def project(timing, plan, previous):
    candidates, by_arm, hits = inputs()
    need(candidates == plan["groups"] and previous["method"] == X["METHOD"], "same chosen cohorts")
    basis, _, _ = F["freeze"]()
    rates = {
        s: timing["classes"][s]["reduction_ppm"] if s in candidates else [0, PPM] for s in SHAPES
    }
    result = {}
    for tag, per_job in by_arm.items():
        arm = basis["arms"][tag]
        full = {i: sum(weights.values()) for i, weights in per_job.items()}
        models = {}
        for name, placed in (("paid", False), ("favorable", True)):

            def clock(cut, arm=arm, placed=placed, tag=tag):
                return F["clock"](F["adjusted"](arm, cut), hits, placed, False, tag)

            need(
                clock(full) == previous["arms"][tag]["modes"][name]["simultaneous"]["full"],
                "full exposure",
            )
            low, high = [
                {
                    i: sum(v * rates[s][side] for s, v in weight.items()) // PPM
                    for i, weight in per_job.items()
                }
                for side in (0, 1)
            ]
            models[name] = {
                k: clock(cut) for k, cut in (("zero", {}), ("low", low), ("high", high))
            }
            prior_zero = json.loads((X["ORIGINAL"] / "victims.json").read_bytes())["arms"][tag][
                "modes"
            ][name]["baseline"]
            need(models[name]["zero"] == prior_zero, "zero exposure")
        result[tag] = models
    margins = {
        name: {
            side: min(V["budget"](m[name][side]) for m in result.values())
            for side in ("low", "high")
        }
        for name in ("paid", "favorable")
    }
    status = (
        "NO_GO_AT_CALIBRATED_RATES"
        if margins["favorable"]["high"] < 0
        else "GO_CAUSAL_CAPTURE_FIXTURE"
        if margins["paid"]["low"] >= 0
        else "INCONCLUSIVE"
    )
    return dict(
        status=status,
        evidence="MEASURED_DEVICE_TRACE_DERIVED_CLIENT",
        rates_ppm=rates,
        margins_ns=margins,
        arms=result,
        requests=0,
    )


def physical(a, receipt):
    IO["run"](
        a,
        receipt,
        protocol=METHOD,
        source=HERE / "mixed-device.md",
        parse=parse,
        maximum_bytes=30_000_000_000,
        requested_records=lambda timing, _: timing["requested_records"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    for action, keys in (
        ("build", ("previous",)),
        ("plan", ("mixed", "manifest")),
        ("grade", ("mixed", "observed", "plan")),
    ):
        p = subs.add_parser(action)
        for key in (*keys, "new-output-dir"):
            p.add_argument("--" + key, type=lambda x: Path(x).resolve(), required=True)
    q = subs.add_parser("check")
    q.add_argument("folder", type=Path)
    a = parser.parse_args()
    need(sha(HERE / "mixed-device.md") == METHOD, "registered experiment")
    if a.action == "check":
        z = a.folder
        meta = json.loads((z / "device.json").read_bytes())
        timing = parse((z / "service.txt").read_text().splitlines(), meta["plan"])
        need(
            timing == meta["timing"] and sha(z / "service.txt") == meta["stdout_sha256"],
            "physical receipt",
        )
        new = project(timing, meta["plan"], M["verified"](z / "mixed.json", MIXED))
        need(new == json.loads((z / "projection.json").read_bytes()), "published projection")
        print(new["status"], new["margins_ns"])
        return
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        commit, tree = M["B"]["version"]()
        if a.action == "grade":
            obs = json.loads((a.observed / "receipt.json").read_bytes())
            need(
                obs["status"] == "MEASURED"
                and obs["protocol"] == METHOD
                and (obs["commit"], obs["tree"]) == (commit, tree),
                "physical authority",
            )
            spec = M["verified"](a.plan / "receipt.json", obs["plan_sha256"])
            need(sha(a.observed / "stdout") == obs["stdout_sha256"], "raw service")
            timing = parse((a.observed / "stdout").read_text().splitlines(), spec)
            need(timing == obs["timing"], "same local grade")
            new = project(timing, spec, M["verified"](a.mixed, MIXED))
            save(a.new_output_dir / "projection.json", new)
            print(new["status"], new["margins_ns"])
        else:
            rec = (plan if a.action == "plan" else build)(a)
            save(
                a.new_output_dir / "receipt.json",
                rec
                | dict(
                    status="PASS", protocol=METHOD, commit=commit, tree=tree, program=sha(__file__)
                ),
            )
            print("PASS", sha(a.new_output_dir / "receipt.json"))
    except Exception as e:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(e)))
        raise


if __name__ == "__main__":
    main()
