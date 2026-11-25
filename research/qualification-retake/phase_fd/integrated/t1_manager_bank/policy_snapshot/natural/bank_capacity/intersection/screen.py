"""Seal T1 publication tails, then count the additional distinct compulsory intersections."""

import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[4] / "t1_source_bank"
PROTOCOL = "3b8d87996c606eeee28e07dd53c9316873f6dce682fc5ec5c8ed4c9b37c175fb"
SOURCE = "0fe604032499bbf607dd23e9fcd547d8266703f8908d13e2e62eeaf8bb7d5444"
HISTORY = "f2e1232d2466835931bdbe43420a61cb05fd0d473705c42ea5c5fbcabe87f049"
CAPACITY = "c35a0afbfbe947927e311100a84d2be883df7d41e026eb7a5ac1d06e27873147"
PREFIX = "7c0ef30ca09fca94e1f8be7c178f7a43ab1a9a9f3e9a1fe2e0da792b4fa6a3b2"
SIZES = (353, 386, 390)
RATE = 4_500_000_000


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load():
    require(sha(HERE / "protocol.md") == PROTOCOL and sha(OLD / "screen.py") == SOURCE, "procedure")
    proc = run_path(str(OLD / "screen.py"))
    proc["pin_programs"]()
    src = proc["src"]
    history = src.pinned(OLD / "receipt.json", HISTORY)
    capacity = src.pinned(HERE.parent / "receipt.json", CAPACITY)
    require(
        capacity["envelopes"]["part40_process"]["arms"]["raw"]["slots"] == SIZES[-1]
        and capacity["envelopes"]["fixed_K353"]["arms"]["charged_spatial"]["slots"] == SIZES[1],
        "pre-registered capacities",
    )
    return proc, history


def seal(part, proc, history):
    src, control = proc["src"], proc["control"]
    rows = control["prefix_records"](part)
    require(len(rows) == 47_303 and src.audit.record_digest(rows) == PREFIX, "T1 prefix")
    slots, fifo, _ = src.audit.state_before(rows)
    require(
        len(slots) == 36 * 40 and not fifo and all(s in (0, 2) and not c for _, _, s, c in slots),
        "primary and worker drain",
    )
    feed, counts = proc["offers"](rows)
    banks = {}
    for k in SIZES:
        bank, _, _, washout = control["maintain"](feed, k)
        require(washout is not None and len(bank) == len(set(bank)) == k, "unwashed initial bank")
        banks[str(k)] = {
            "keys": bank,
            "ordered_keys_sha256": src.audit.digest(bank),
            "washout_offer": washout + 1,
        }
    require(
        banks["353"]["ordered_keys_sha256"] == history["t1"]["ordered_hash"]["source"]
        and all(banks["390"]["keys"][-k:] == banks[str(k)]["keys"] for k in SIZES),
        "historical bank and recency nesting",
    )
    return {
        "archive_manifest_sha256": src.PART,
        "prefix_sha256": PREFIX,
        "prefix_records": len(rows),
        "feed_sha256": src.audit.digest(feed),
        "qualified_offers": len(feed),
        "distinct_offers": len({key for key, _ in feed}),
        "incomplete_inherited": sum(c["incomplete_inherited"] for c in counts.values()),
        "banks": banks,
    }


def members(pools):
    return {(layer, e) for layer, pool in enumerate(pools) for e in pool if e >= 0}


def score(part, proc, history, selection, seal_hash):
    src = proc["src"]
    seal_data = src.pinned(selection, seal_hash)
    require(json.loads(json.dumps(seal(part, proc, history))) == seal_data, "T1 escrow")
    work, _ = proc["t2"](part)
    initial, final, waves = work
    start, restored = members(initial), members(final)
    demand = {(layer, e) for call, layer, experts in waves if call <= 2 for e in experts}
    needed = (demand | restored) - start
    banks = {k: set(map(tuple, seal_data["banks"][str(k)]["keys"])) for k in SIZES}
    require(
        len(needed) == history["t2"]["lru_off"]["compulsory_disk_with_restore"]
        and len(needed - banks[353]) == history["t2"]["lru_source"]["compulsory_disk_with_restore"]
        and len(needed - banks[353]) == 839,
        "historical floors",
    )

    def counts(group):
        tiers = src.audit.per_tier(group)
        require(sum(tiers.values()) == len(group), "tier partition")
        return dict(total=len(group), **tiers)

    budgets = history["conditional_volume_budgets"]
    require(budgets == {"47": 10_690_306_614, "46": 11_440_306_616}, "volume gates")
    pay, pack = proc["PAY"], proc["PACK"]
    arms = {}
    for k, bank in banks.items():
        extra = bank - banks[353]
        useful, resident = extra & needed, extra & start
        other = extra - useful - resident
        floor = len(needed - bank)
        require(
            len(extra) == k - 353 == len(useful) + len(resident) + len(other)
            and floor == 839 - len(useful) == proc["causal"]["compulsory"](*work, bank, True),
            "marginal conservation and compulsory oracle",
        )
        payload = floor * pay
        aligned = floor * pack
        arms[str(k)] = {
            "ordered_keys_sha256": seal_data["banks"][str(k)]["ordered_keys_sha256"],
            "washout_offer": seal_data["banks"][str(k)]["washout_offer"],
            "bank_already_primary": counts(bank & start),
            "bank_useful": counts(bank & needed),
            "extra_already_primary": counts(resident),
            "extra_useful": counts(useful),
            "extra_absent_but_unused": counts(other),
            "distinct_compulsory": counts(needed - bank),
            "floor_payload_bytes": payload,
            "floor_aligned_pack_requested_bytes": aligned,
            "floor_payload_time_at_assumed_rate_s": payload / RATE,
            "payload_reduction_from_353_bytes": len(useful) * pay,
            "floor_payload_time_reduction_at_assumed_rate_s": len(useful) * pay / RATE,
            "scenario": {
                d: {
                    "floor_pass": payload <= cap,
                    "max_full_payloads": cap // pay,
                    "excess_payload_bytes": payload - cap,
                    "excess_payload_time_at_assumed_rate_s": (payload - cap) / RATE,
                }
                for d, cap in budgets.items()
            },
        }
    return {
        "status_by_decode_denominator": {
            d: "NO_GO_DISTINCT_FLOOR_K353_TO_K390"
            if not arms["390"]["scenario"][d]["floor_pass"]
            else "INCONCLUSIVE"
            for d in budgets
        },
        "timing": "INCONCLUSIVE",
        "journal_sha256": proc["JOURNAL"],
        "original_capture_sha256": src.FAIL,
        "original_capture_status": "FAIL_PRESERVED",
        "selection_sha256": seal_hash,
        "history_sha256": HISTORY,
        "capacity_sha256": CAPACITY,
        "archive_manifest_sha256": src.PART,
        "t1": {k: v for k, v in seal_data.items() if k != "banks"},
        "t2": {
            "initial_members": counts(start),
            "restored_members": counts(restored),
            "prefill_distinct_demand": counts(demand),
            "absent_from_initial_demand_or_restore": counts(needed),
            "absent_from_initial_restore_only": counts(restored - start - demand),
        },
        "rate_bytes_s": RATE,
        "payload_bytes": pay,
        "aligned_pack_requested_bytes": pack,
        "arms": arms,
        "new_model_forwards": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--part", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--selection-sha256")
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700)
    status = 0
    try:
        proc, history = load()
        if args.action == "seal":
            result = seal(args.part, proc, history)
            name = "selection.json"
        else:
            require(args.selection and args.selection_sha256, "T1 selection and checksum required")
            result = score(args.part, proc, history, args.selection, args.selection_sha256)
            name = "receipt.json"
    except Exception as exc:
        name = "receipt.json"
        result = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if isinstance(exc, FileNotFoundError)
            else "FAIL_PRESERVED",
            "error": f"{type(exc).__name__}: {exc}",
        }
        status = 1
    if args.action != "seal" or status:
        result.update(program_sha256=sha(Path(__file__)), protocol_sha256=PROTOCOL)
    tmp = out / "output.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(out / name)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
