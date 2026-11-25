"""Recheck the sealed terminal receipt and every loader log from a movable archive."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

RAW_SHA = "9e553bcfa3dd8889100c8836bc3b873491248567672f93e7859e7f8b76e35116"
MODES = ("original", "off", "on")


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compact(raw):
    receipt = (raw / "receipt.json").read_bytes()
    check(digest(receipt) == RAW_SHA, "terminal receipt")
    data = json.loads(receipt)
    check(data["status"] == "PASS_C281_C291_STATIC_CLOSURE", "unqualified closure")
    startup = data["startup"]
    consumers = sorted(data["consumers"])
    modes = data["per_mode"]
    expected_queries = {"dynamic-" + name for name in [*startup, "server"]}
    expected_queries.add("original-end")
    for mode in MODES:
        expected_queries.add(mode + "-verify")
        for root in consumers:
            expected_queries.update(mode + "-" + root + "-" + k for k in ("list", "relocations"))
    check(
        set(data["queries"]) == expected_queries and len(expected_queries) == 53, "query coverage"
    )
    for tag, result in data["queries"].items():
        check(result["returncode"] == 0, "query failed")
        for ext, side in (("out", "stdout"), ("err", "stderr")):
            payload = (raw / (tag + "." + ext)).read_bytes()
            check(digest(payload) == result[side + "_sha256"], "modified query log")
            if side == "stderr":
                check(not payload, "unexpected query diagnostic")
    check(modes["off"] == modes["on"], "OFF/ON provider maps differ")
    for mode in MODES:
        check(sorted(modes[mode]) == consumers, "consumer population")
    for root in consumers:
        old, new = modes["original"][root], modes["on"][root]
        check(old.keys() == new.keys(), "provider population")
        check([k for k in old if old[k] != new[k]] == ["libllama.so.0"], "wrong provider delta")
    fields = (
        "status",
        "commit",
        "tree",
        "elapsed_ns",
        "final_scope",
        "driver_deployment",
        "original_and_candidate_rejected_as_each_other",
        "server_processes",
        "backend_enumerations",
        "model_processes",
        "transformer_forwards",
        "payload_read_bytes",
    )
    return {
        **{k: data[k] for k in fields},
        **{k: v for k, v in data.items() if k.endswith("_sha256")},
        "raw_receipt_sha256": RAW_SHA,
        "queries_verified": len(expected_queries),
        "logs_verified": 2 * len(expected_queries),
        "direct_consumers": consumers,
        "providers_per_root_each_mode": {r: len(modes["off"][r]) for r in consumers},
        "startup_candidate_sha256": {name: row["sha256"] for name, row in startup.items()},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    args = parser.parse_args()
    json.dump(compact(args.raw), sys.stdout, indent=2, sort_keys=True)
    print()
