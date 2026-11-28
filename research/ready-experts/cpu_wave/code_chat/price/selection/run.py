"""Price a past-only unanimity rule against the observed native intervals in each matched pair."""

import argparse
import hashlib
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
REVIEW = run_path(HERE.parent / "review.py")
F, LOOK, need, read, sha, publish = (
    REVIEW[k] for k in ("F", "LOOK", "need", "read", "sha", "publish")
)


def eligible(history, proposal):
    key = history[-2:]
    matches = 0
    for i in range(len(history) - 3):
        if history[i : i + 2] == key:
            if history[i + 2 : i + 4] != proposal:
                return False
            matches += 1
    return matches >= 2


def sampled(root, arm):
    native = F["H"]["T"]["V"]
    directory = root / arm["folder"]
    unit = arm["unit"]
    checked = F["H"]["G"]["read"]
    receipt = checked(directory / "receipt.json", arm["receipt_sha256"])
    session = checked(directory / "session.json", receipt["trial"]["session_sha256"])
    monitor = checked(directory / "raw" / (unit + ".json"), session["monitor_sha256"])
    data = (directory / "raw" / (unit + ".stderr")).read_bytes()
    need(hashlib.sha256(data).hexdigest() == monitor["output_sha256"][".stderr"], "journal digest")
    rows = list(native["events"](data))
    tasks = [t for _, t, e in rows if e == ("start",)]
    need(len(tasks) == 2 and tasks[0] != tasks[1], "two independent tasks")
    values = [(t, e[3]) for t, task, e in rows if task == tasks[1] and e[0] == "sample"]
    ticks = [((m * 60 + s) * 1_000_000 + ms * 1000 + us) * 1000 for (m, s, ms, us), _ in values]
    digest = native["digest"](native["ids_bytes"]([v for _, v in values]))
    p = arm["price"]
    need(
        len(ticks) == 256
        and ticks[-1] - ticks[0] == p["native_span_ns"]
        and all(a <= b for a, b in pairwise(ticks))
        and digest == arm["trajectories"]["2"]["sampled_sha256"],
        "native trajectory",
    )
    return ticks


def pair(steps, decisions, c, b, cut):
    result = {}
    for label, stop in (("first_final_native", cut), ("full", len(c) - 1)):
        by_depth = {}
        filter_gain = oracle = positive = 0
        all_block = all_ordinary = serial_sum = 0
        for row, use in zip(steps, decisions, strict=True):
            i = row["at"] - 1
            if i >= stop:
                break
            j = min(i + row["emitted"], stop)
            serial = c[j] - c[i]
            actual = b[j] - b[i]
            gain = serial - actual
            serial_sum += serial
            if row["proposal"]:
                d = by_depth.setdefault(
                    str(row["accepted"]), dict(n=0, control_ns=0, on_ns=0, chosen=0)
                )
                d["n"] += 1
                d["control_ns"] += serial
                d["on_ns"] += actual
                d["chosen"] += use
                all_block += gain
                filter_gain += gain if use else 0
                oracle += max(gain, 0)
                positive += gain > 0
            else:
                all_ordinary += gain
        need(
            serial_sum == c[stop] - c[0]
            and all_block + all_ordinary == serial_sum - (b[stop] - b[0]),
            "conservation at native cut",
        )
        result[label] = dict(
            sample=stop + 1,
            by_accepted=by_depth,
            filter_gain_ns=filter_gain,
            oracle_gain_ns=oracle,
            observed_profitable_blocks=positive,
            all_block_gain_ns=all_block,
            ordinary_gain_ns=all_ordinary,
        )
    return result


def measure(a):
    r = F["H"]["G"]["read"](a.review, a.review_sha256)
    REVIEW["compact"](r)
    family = F["H"]["G"]["read"](a.family / "receipt.json", r["family_sha256"])
    replay_hash = read(F["CHAT"] / "lookup.json")["steps_sha256"]
    steps = F["H"]["G"]["read"](a.replay / "steps.json", replay_hash)["T2"]
    results = {}
    digest = None
    for on, controls in ((2, (0, 1)), (3, (5, 4))):
        buyer = r["arms"][on]
        ticks = sampled(a.family, buyer)
        for index in controls:
            arm = r["arms"][index]
            need(arm["folder"] == family["arms"][index]["folder"], "paired process")
            entry, ref, cut, _ = LOOK["evidence"](
                a.family / arm["folder"], dict(unit=arm["unit"], target_ids=arm["trajectories"])
            )
            need(
                ref == sampled(a.family, arm)
                and cut is not None
                and cut + 1 == arm["price"]["conditional"]["first_final_sample"]
                and F["H"]["SESSION"].ids_hash(entry["prompt"])
                == arm["turns"][1]["official_ids_sha256"],
                "serial native cut",
            )
            outputs = entry["target"]
            prefix = entry["prompt"] + outputs[:1]
            choices = []
            for row in steps:
                i, prop = row["at"], row["proposal"]
                need(len(prefix) == len(entry["prompt"]) + i, "prefix frontier")
                choices.append(bool(prop) and eligible(prefix, prop))
                emitted = outputs[i : i + row["emitted"]]
                accepted = 0
                for v in emitted:
                    if accepted == len(prop) or v != prop[accepted]:
                        break
                    accepted += 1
                need(
                    accepted == row["accepted"] and len(emitted) == accepted + 1,
                    "shadow frontier including correction or bonus",
                )
                prefix.extend(emitted)
            need(
                prefix == entry["prompt"] + outputs
                and sum(bool(s["proposal"]) for s in steps) == 46,
                "complete input",
            )
            key = hashlib.sha256(bytes(choices)).hexdigest()
            need(digest in (None, key), "identical causal selection")
            digest = key
            results[buyer["folder"] + "/" + arm["folder"]] = pair(steps, choices, ref, ticks, cut)
    positive = all(c["filter_gain_ns"] > 0 for v in results.values() for c in v.values())
    return dict(
        status="TRACE_DERIVED_FIXED_INTERVALS",
        decision="GO_SELECTIVE_FIXTURE" if positive else "NO_GO_THIS_FILTER",
        comparison=results,
        selected=sum(choices),
        proposed=46,
        choices_sha256=digest,
        review_sha256=a.review_sha256,
        steps_sha256=replay_hash,
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(HERE / "run.py"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("family", "replay", "review", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--review-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = measure(a)
        publish(a.new_output_dir / "receipt.json", r)
    except Exception as exc:
        publish(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise
    print(r["decision"], r["selected"])
