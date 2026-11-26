"""Decode hits requiring first-publication retention or an encoded resident carried across I."""

import argparse
import hashlib
import json
import resource
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
sys.path.insert(0, str(UNIT))
from l2_read_admission import screen as source  # noqa: E402
from l2_read_admission.oracle import maximum_hits  # noqa: E402

PREVIOUS = UNIT / "l2_read_admission/evidence/receipt.json"
PREVIOUS_SHA = "9aaa85ad2507d3f67803b51876271ecbc2de33fbab44f26f98afbd54aea40956"
FILTERS = ("full", "no_first_publication", "no_carry_from_increment", "neither")


def classify(jobs):
    previous = {}
    rows = {name: [] for name in FILTERS}
    split = Counter()
    for phase in source.PHASES:
        for claim, publish, key in jobs[phase]:
            if key in previous and phase == "decode":
                start, first, left_phase = previous[key]
                source.require(start < claim, "overlapping generations for one key")
                after_i = left_phase == "decode"
                tags = (True, not first, after_i, not first and after_i)
                group = "first" if first else "repeat"
                tier = source.TIERS[key[0]]
                split[(group, left_phase, tier)] += 1
                for name, keep in zip(FILTERS, tags, strict=True):
                    if keep:
                        rows[name].append((start, claim, tier))
            previous[key] = (publish, key not in previous, phase)
    return rows, split


def assess(rows, capacity, reads):
    gate = (reads + 4) // 5
    out = {}
    for name, items in rows.items():
        ceiling = maximum_hits([(a, b) for a, b, _ in items], capacity)
        by_tier = {}
        for tier in ("CPU", "CUDA0"):
            group = [(a, b) for a, b, t in items if t == tier]
            by_tier[tier] = {
                "eligible_intervals": len(group),
                "ceiling_assuming_whole_capacity": maximum_hits(group, capacity),
            }
        out[name] = {
            "eligible_intervals": len(items),
            "ceiling_hits": ceiling,
            "gate": "NO_GO_RESTRICTED" if ceiling < gate else "HEADROOM_ONLY",
            "gate_shortfall_hits": max(0, gate - ceiling),
            "tier_diagnostics_not_additive": by_tier,
        }
    return {
        "capacity": capacity,
        "decode_reads": reads,
        "ceil_20pct_hits": gate,
        "restrictions": out,
    }


def analyse(raw):
    prior = json.loads(source.warm.checked(PREVIOUS, PREVIOUS_SHA))
    source.require(
        prior["status"] == "TRACE_DERIVED_FIXED_PRIMARY"
        and prior["manifest_sha256"] == source.boundary.MANIFEST_SHA,
        "previous source",
    )
    for name in ("screen.py", "oracle.py", "protocol.md"):
        source.warm.checked(UNIT / "l2_read_admission" / name, prior["sources_sha256"][name])
    source.require(set(prior["arms"]) == set(source.boundary.NAMES), "four arms required")
    result = {}
    for name in source.boundary.NAMES:
        jobs, identity = source.service_arm(raw, name)
        anchor = prior["arms"][name]
        source.require(all(identity[k] == anchor[k] for k in identity), "arm identity")
        rows, split = classify(jobs)
        scenarios = {}
        for cap_name, capacity in (("3GiB", 243), ("E20_payload_only", 378)):
            report = assess(rows, capacity, len(jobs["decode"]))
            old = anchor["scenarios"][cap_name]["offline"]
            expected_hits = {"nominal153": {243: 275, 378: 292}, "code153": {243: 266, 378: 401}}
            case = name.split("-")[1]
            source.require(
                old["capacity"] == capacity
                and old["decode_reads"] == report["decode_reads"]
                and report["restrictions"]["full"]["ceiling_hits"]
                == old["decode_only_hits"]
                == expected_hits[case][capacity],
                "full oracle disagrees",
            )
            scenarios[cap_name] = report
        result[name] = {
            **identity,
            "left_publication_class_counts": {"/".join(k): v for k, v in sorted(split.items())},
            "scenarios": scenarios,
        }
    return {
        "status": "TRACE_DERIVED_INFORMATION_REQUIREMENTS",
        "previous_sha256": PREVIOUS_SHA,
        "manifest_sha256": source.boundary.MANIFEST_SHA,
        "arms": result,
        "interpretation": "Each restricted shortfall is separately necessary for 20% coverage. "
        "The two membership conditions overlap. No ceiling sums across tiers.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    a = parser.parse_args()
    out = a.new_output_dir.resolve()
    source.require(not out.is_relative_to(a.raw_dir.resolve()), "protect raw")
    out.mkdir(mode=0o700)
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))

    def timeout(_signum, _frame):
        raise TimeoutError("120 s replay limit")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(120)
    try:

        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1", *args],
                cwd=HERE,
                text=True,
            ).strip()

        commit, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        source.require(
            not git("status", "--porcelain=v1", "--untracked-files=normal"), "dirty checkout"
        )
        answer = analyse(a.raw_dir)
        answer.update(commit=commit, tree=tree, clean=True)
    except FileNotFoundError as e:
        answer = {"status": "NOT_RUN_RAW_REQUIRED", "missing": str(e.filename)}
    except (
        OSError,
        ValueError,
        MemoryError,
        TypeError,
        KeyError,
        subprocess.CalledProcessError,
    ) as e:
        answer = {"status": "FAIL_PRESERVED", "reason": str(e)}
    finally:
        signal.alarm(0)
    answer["sources_sha256"] = {
        x.name: hashlib.sha256(x.read_bytes()).hexdigest()
        for x in (Path(__file__).resolve(), HERE / "protocol.md")
    }
    temp = out / "receipt.pending"
    with temp.open("x") as f:
        f.write(json.dumps(answer, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temp.rename(out / "receipt.json")
    print(answer["status"])
    return int("arms" not in answer)


if __name__ == "__main__":
    raise SystemExit(main())
