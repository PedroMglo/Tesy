"""Make a bounded online cache decision from T1. Score it in a separate process."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RES = run_path(str(HERE / "residency.py"))
BASE, SRC, require = (RES[k] for k in ("BASE", "SRC", "require"))
PROFILE = SRC["Q"]["PROFILE"]
T1_SEAL = "c25153fdb39d7776088645f0f9c10ca848fe99d45f1ed2092a17663c79615845"
RES_RESULT = "82230ddf6d1527b4fc5d3a540afe91a8aeda5f11c671ca7f97c24ead37a9fb8a"
METHOD = "fb5ee465f813f2116762250f42ab61567bf9fa02ec06db3e905de6272d463247"
WAVE_METHOD = "9c1e9dda248402f72e0ce1fd634f8212c959662e53d4fab97e8de03c57d11e94"
EXPECTED_EVENTS = {
    9: "wave_begin",
    10: "demand",
    13: "dispatch",
    16: "set",
    23: "wave_end",
    30: "read",
}


class PublicationBank(SRC["Q"]["POLICY"]["VictimBank"]):
    def __init__(self, capacity):
        super().__init__(capacity, use_prefill=False)
        self.delay_ns = Counter()

    def published(self, expert, elapsed):
        require(elapsed >= 0, "publication before reserve")
        self.delay_ns[expert] += elapsed

    def priority(self, key):
        return self.delay_ns[key], self.held[key], key


def train(arm):
    require(
        SRC["digest"](HERE / "selection-observation.md") == METHOD
        and SRC["digest"](HERE / "selection-protocol.md") == WAVE_METHOD,
        "selection protocol",
    )
    seal = SRC["pinned"](arm / "before-t2.json", T1_SEAL)
    journal = arm / "observer/events.pfj"

    def prefix():
        return PROFILE["iter_rows"](journal, 0, seal["records"])

    grade, _ = PROFILE["prefix_grade"](prefix(), PROFILE["T1"], 9)
    require(
        all(v == seal[k] for k, v in grade.items()) and seal["records"] == 87_736,
        "unverified before-POST prefix",
    )
    bank = PublicationBank(RES["BUDGET"])
    slots, pending, counts = {}, {}, Counter()
    for row in prefix():
        counts[row.kind] += 1
        loc = row.layer, row.slot
        key = SRC["key"](row)
        if row.kind == 5:
            require(loc not in slots and row.a in (0, 2), "initial slot")
            slots[loc] = (row.gen, row.expert, row.a)
        elif row.kind == 11:
            gen, old, state = slots[loc]
            require((old, gen + 1) == (row.a, row.gen) and state in (0, 2), "stale eviction")
            if state == 2:
                bank.offer((row.layer, old))
            slots[loc] = (row.gen, row.expert, 1)
            pending[key] = row.ns
        elif row.kind == 17:
            require(slots[loc] == (row.gen, row.expert, 1), "stale publication")
            bank.published((row.layer, row.expert), row.ns - pending.pop(key))
            slots[loc] = (row.gen, row.expert, 2)
    require(
        not pending and len(bank.held) == RES["BUDGET"] and sum(counts.values()) == seal["records"],
        "bank or journal conservation",
    )
    missing = [name for k, name in EXPECTED_EVENTS.items() if not counts[k]]
    # This prefix is immutable. A future full observation gets a new protocol and identity.
    require(bool(missing), "full-service source requires its own training run")
    keys = [list(k) for k in sorted(bank.held)]
    identity = hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()
    account = bank.receipt()
    return {
        "schema": "tesy.causal_publication_bank.v1",
        "status": "CAUSAL_PLAN_SEALED",
        "protocol_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "prefix_sha256": grade["sha256"],
        "records_read": seal["records"],
        "prefix_event_counts": dict(sorted((str(k), v) for k, v in counts.items())),
        "wave_cost_policy": {"status": "NOT_RUN_RAW_REQUIRED", "missing_observations": missing},
        "acquisition": account,
        "acquired_payload_bytes": sum(account["copies"].values()) * RES["PAYLOAD"],
        "keys_sha256": identity,
        "keys": keys,
    }


def score(archive, path, plan_sha):
    plan = SRC["pinned"](path, plan_sha)
    t1 = archive / "part-106" / SRC["SOURCES"]["P106"][0] / "ON"
    require(train(t1) == plan, "candidate did not come exclusively from the sealed prefix")
    bank = set(map(tuple, plan["keys"]))
    prior = SRC["pinned"](
        BASE["NATURAL"] / "prefill_retention/request_cost/receipt.json", BASE["PRIOR"]
    )
    controls = SRC["pinned"](HERE / "residency-result.json", RES_RESULT)
    arms, same = {}, None
    for label in ("P106", "P97"):
        name, sha, _ = SRC["SOURCES"][label]
        root = archive / ("part-" + label[1:]) / name
        (calls, _, _), auth = BASE["read_arm"](archive, label, prior[label])
        if label == "P106":
            _, rows, tiers, _ = SRC["Q"]["read_new"](root, sha)
        else:
            rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
            receipt = json.loads((root / "ON/receipt.json").read_bytes())
            log = root / "ON/raw" / receipt["native_ids"]["raw_stderr_file"]
            tiers, _ = SRC["T"]["mapping"](log.read_bytes(), rows)
        groups, _, origins = RES["raw_groups"](rows, tiers)
        lineage = (origins, SRC["Q"]["bindings"](rows), auth["trajectory_sha256"])
        require(same is None or same == lineage, "T2 controls differ")
        same = lineage
        args = (calls, groups, auth["outside_calls_ns"])
        original = controls["arms"][label]["cases"]
        require(RES["bounds"](*args) == original["no_bank"], "ablation mismatch")
        arms[label] = {}
        for mode, direct in (("copied", False), ("direct", True)):
            candidate = RES["bounds"](*args, bank=bank, direct=direct)
            arms[label][mode] = {
                **candidate,
                "first_gain_over_control_ns": {
                    name: original[key]["first_final"] - candidate["first_final"]
                    for name, key in (
                        ("empty", "no_bank"),
                        ("lru", "lru_" + mode),
                        ("frequency", "prefill_" + mode),
                    )
                },
            }
    paid = [a["copied"] for a in arms.values()]
    direct = [a["direct"] for a in arms.values()]
    if all(BASE["joint"](c) >= 0 and c["first_gain_over_control_ns"]["lru"] >= 0 for c in paid):
        decision = "GO_DELIVERY_FIXTURE_ONLY"
    elif any(BASE["joint"](c) < 0 for c in direct) or all(
        c["first_gain_over_control_ns"]["lru"] < 0 for c in paid
    ):
        decision = "NO_GO_THIS_POLICY_AND_BUDGET"
    else:
        decision = "INCONCLUSIVE"
    return {
        "schema": "tesy.causal_bank_test.v1",
        "status": "TRACE_DERIVED",
        "decision": decision,
        "selection": {k: v for k, v in plan.items() if k != "keys"},
        "plan_sha256": plan_sha,
        "residency_results_sha256": RES_RESULT,
        "arms": arms,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    make = modes.add_parser("train")
    make.add_argument("--t1-arm", type=Path, required=True)
    test = modes.add_parser("score")
    test.add_argument("--archive", type=Path, required=True)
    test.add_argument("--plan", type=Path, required=True)
    test.add_argument("--plan-sha256", required=True)
    for p in (make, test):
        p.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    is_train = args.mode == "train"
    try:
        result = (
            train(args.t1_arm) if is_train else score(args.archive, args.plan, args.plan_sha256)
        )
    except FileNotFoundError as exc:
        missing = Path(exc.filename).resolve() if exc.filename else None
        raw_root = args.t1_arm if is_train else args.archive
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if missing and missing.is_relative_to(raw_root.resolve())
            else "FAIL",
            "missing_file": missing.name if missing else None,
        }
    except (AssertionError, KeyError, OSError, TypeError, ValueError) as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    tmp = args.new_output_dir / ".pending"
    with tmp.open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    tmp.rename(args.new_output_dir / ("plan.json" if is_train else "receipt.json"))
    print(result["status"], result.get("decision", result.get("reason", "")))
    return int(result["status"] not in ("CAUSAL_PLAN_SEALED", "TRACE_DERIVED"))


if __name__ == "__main__":
    raise SystemExit(main())
