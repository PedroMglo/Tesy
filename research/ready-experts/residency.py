"""Price exact resident bytes before scheduling each observed group of four workers."""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BASE = run_path(str(HERE / "screen.py"))
SRC = BASE["SOURCE"]
require = BASE["require"]
MODEL_EXPERTS = 36 * 128
PAYLOAD = 13_219_200
BUDGET = 353
METHOD = "e44c937f196bde22da15cbd876740a3326143c6f2e3224fc1066e6dd1d244281"
FIRST_RESULT = "56ff1216a041492d6ab3bc8c0519c5ddebfc4f449b58199d107a5a4016e8625a"


@dataclass(frozen=True)
class Job:
    expert: tuple[int, int]
    read_ns: int
    set_ns: int


def raw_groups(rows, tiers):
    waves, origins = SRC["timeline"](rows)
    reads = {}
    for event in rows:
        if event.kind == 30:
            key = SRC["key"](event)
            require(key not in reads and event.ns >= event.begin > 0, "duplicate or invalid READ")
            reads[key] = event.ns - event.begin
    require(reads.keys() == origins.keys(), "incomplete READ population")
    groups = defaultdict(lambda: defaultdict(list))
    worker = defaultdict(Counter)
    for wave in waves:
        for key, paid in wave.required_service.items():
            layer, _, _, expert = key
            read = reads[key]
            require(read <= paid and layer == wave.site[2], "wrong job price or device")
            groups[wave.site[0]][wave.site[1:3]].append(Job((layer, expert), read, paid - read))
            worker[tiers[layer]].update(jobs=1, read_ns=read, set_ns=paid - read)
    return groups, dict(worker), origins


def bounds(calls, groups, exterior, *, uniform=0, bank=None, direct=False, free_set=False):
    """All intermediate service prices use units of ns / MODEL_EXPERTS."""
    require(0 <= uniform <= MODEL_EXPERTS and not (uniform and bank), "invalid placement")
    buckets = defaultdict(Counter)
    for c in calls:
        s = buckets[BASE["phase"](c.number)]
        floor = 0
        for jobs in groups[c.number].values():
            prices = []
            for job in jobs:
                saved = MODEL_EXPERTS if bank and job.expert in bank else uniform
                remaining = MODEL_EXPERTS - saved
                transfer = 0 if free_set else job.set_ns * (remaining if direct else MODEL_EXPERTS)
                prices.append(job.read_ns * remaining + transfer)
                s["full_hits"] += int(saved == MODEL_EXPERTS)
                s["partial_hits"] += int(0 < saved < MODEL_EXPERTS)
            floor += BASE["layer_fourths"](prices)
        service = (floor + 4 * MODEL_EXPERTS - 1) // (4 * MODEL_EXPERTS)
        s["floor_ns"] += max(c.span - c.remap, service)
    p, b, z = (buckets[k]["floor_ns"] for k in ("prefill", "decode_before_final", "decode_tail"))
    first = exterior["first_final"] + p + b
    decode = exterior["decode"] + b + z
    return {
        "first_final": first,
        "decode": decode,
        "margin_ns": BASE["margins"](first, decode),
        "phases": dict(buckets),
    }


def min_capacity(fits):
    if fits(0):
        return 0
    if not fits(MODEL_EXPERTS):
        return None
    no, yes = 0, MODEL_EXPERTS
    while yes - no > 1:
        mid = (no + yes) // 2
        if fits(mid):
            yes = mid
        else:
            no = mid
    return yes


def run(archive):
    require(SRC["digest"](HERE / "residency-protocol.md") == METHOD, "unsealed protocol")
    basis = SRC["pinned"](HERE / "overlap-result.json", FIRST_RESULT)
    prior = SRC["pinned"](
        BASE["NATURAL"] / "prefill_retention/request_cost/receipt.json", BASE["PRIOR"]
    )
    name, family_sha, _ = SRC["SOURCES"]["P106"]
    sealed, rows106, tiers106, _ = SRC["Q"]["read_new"](archive / "part-106" / name, family_sha)
    banks = {n: set(map(tuple, v["ordered_keys"])) for n, v in sealed["banks"].items()}
    require(
        set(banks) == {"lru", "prefill"} and all(len(b) == BUDGET for b in banks.values()),
        "causal bank population",
    )
    cases = {
        "no_bank": {},
        "no_set": {"free_set": True},
        "no_read": {"uniform": MODEL_EXPERTS},
        "uniform_copied": {"uniform": BUDGET},
        "uniform_direct": {"uniform": BUDGET, "direct": True},
    }
    for name, keys in banks.items():
        cases[name + "_copied"] = {"bank": keys}
        cases[name + "_direct"] = {"bank": keys, "direct": True}
    arms, models = {}, {}
    previous = None
    for label in ("P106", "P97"):
        (calls, _, _), auth = BASE["read_arm"](archive, label, prior[label])
        require(auth["clock_ns"] == basis["arms"][label]["clock_ns"], "first study clocks")
        root = archive / ("part-" + label[1:]) / SRC["SOURCES"][label][0] / "ON"
        rows = rows106
        if label == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "raw/events.pfj")
        receipt = json.loads((root / "receipt.json").read_bytes())
        log = root / "raw" / receipt["native_ids"]["raw_stderr_file"]
        tiers, _ = SRC["T"]["mapping"](log.read_bytes(), rows)
        require(tiers == tiers106, "different physical placement")
        groups, workers, origins = raw_groups(rows, tiers)
        bindings = (origins, SRC["Q"]["bindings"](rows), auth["trajectory_sha256"])
        require(previous is None or previous == bindings, "identity of transferred T1 keys")
        previous = bindings
        model = (calls, groups, auth["outside_calls_ns"])
        models[label] = model
        measurements = {name: bounds(*model, **args) for name, args in cases.items()}
        control = measurements["no_bank"]
        require(
            all(control[k] == auth["clock_ns"]["ready"][k] for k in ("first_final", "decode")),
            "no-bank ablation",
        )
        require(sum(w["jobs"] for w in workers.values()) == 1918, "charged jobs")
        arms[label] = {
            "cases": measurements,
            "worker_time_charged_jobs": workers,
            "trajectory_sha256": auth["trajectory_sha256"],
        }

    def evaluate(uniform, direct):
        return {
            name: BASE["joint"](bounds(*model, uniform=uniform, direct=direct))
            for name, model in models.items()
        }

    capacities = {}
    for name, direct in (("copied", False), ("direct", True)):
        count = min_capacity(lambda n, direct=direct: min(evaluate(n, direct).values()) >= 0)
        entry = {"min_expert_equivalents": count, "payload_bytes": None}
        if count is not None:
            entry.update(payload_bytes=count * PAYLOAD, margin_ns_at_min=evaluate(count, direct))
            if count:
                entry["margin_ns_at_one_less"] = evaluate(count - 1, direct)
                require(min(entry["margin_ns_at_one_less"].values()) < 0, "adjacent exclusion")
        capacities[name] = entry
    decisions = {
        c: BASE["consensus"]([BASE["joint"](a["cases"][c]) >= 0 for a in arms.values()])
        for c in cases
    }
    return {
        "schema": "tesy.expert_ready_residency.v1",
        "status": "TRACE_DERIVED",
        "source_sha256": SRC["digest"](Path(__file__)),
        "protocol_sha256": METHOD,
        "overlap_result_sha256": FIRST_RESULT,
        "model_experts": MODEL_EXPERTS,
        "expert_payload_bytes": PAYLOAD,
        "available_expert_equivalents": BUDGET,
        "clock_unit": "ns",
        "arms": arms,
        "decisions": decisions,
        "uniform_minima": capacities,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path, required=True)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    args = cli.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args.archive)
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve() if exc.filename else None
        raw = missing and missing.is_relative_to(args.archive.resolve())
        report = {
            "status": "NOT_RUN_RAW_REQUIRED" if raw else "FAIL",
            "missing_file": missing.name if missing else None,
        }
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        report = {"status": "FAIL", "reason": str(exc)}
    tmp = args.new_output_dir / ".receipt.tmp"
    with tmp.open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    tmp.rename(args.new_output_dir / "receipt.json")
    print(report["status"], report.get("decisions", report.get("reason", "")))
    return 0 if report["status"] == "TRACE_DERIVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
