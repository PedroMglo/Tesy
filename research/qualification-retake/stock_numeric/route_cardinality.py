"""Compare layer-union cardinalities of the measured stock and C294 C110 trajectories."""

import argparse
import hashlib
import json
import re
import runpy
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "nvme_prefix_gate"))
from gate import DIGEST, require, routes, sealed  # noqa: E402

PAIR_SHA = "7d58ea435a1f5b7dff0982f30b7a75ada2aafb8c66ccd54b4fb817ce4484dc1b"
STOCK_SHA = "ebd19afb495957175eedc994a3fa35a069d17d135a3f82c14df62ac16e88715a"


def checked(path, digest):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == digest, "changed receipt")
    return json.loads(data)


def compare(journal, pair_receipt, stock_log):
    stock = checked(HERE / "physical-r1/receipt.json", STOCK_SHA)
    pair = checked(pair_receipt, PAIR_SHA)
    require(pair["status"] == "PASS_PAIRED_SLOTS32_NUMERICAL", "incomplete C294")
    off, on = pair["arms"]
    require(
        [a["mode"] for a in (off, on)] == ["OFF", "ON"]
        and all(a["numerical"]["logits_sha256"] == DIGEST for a in pair["arms"]),
        "incompatible fixture",
    )
    data = sealed(journal, 3058, on["numerical"]["routing"]["sha256"])
    require(on["numerical"]["routing"] == routes(data), "C294 row coverage")
    records = runpy.run_path(str(HERE.parent / "prefix_observer/journal.py"))["records"]
    per_layer = defaultdict(set)
    for row in records(data):
        if row[0] == "row":
            _, call, ub, layer, pos, mode, experts = row
            require(ub == 1 and len(set(experts)) == 4, "expected one ubatch / four experts")
            per_layer[call, layer].update(experts)
    by_layer = [len(per_layer[1, layer]) for layer in range(35)]
    small_calls = [len(per_layer[1, 35])] + [
        sum(len(per_layer[call, layer]) for layer in range(36)) for call in (2, 3)
    ]
    require(small_calls == [4, 144, 144], "C294 one-output rows")
    text = sealed(stock_log, 19199, stock["raw_sha256"]["client.log"]).decode()
    require(
        "36 layers, mxfp4:   161 slots" in text
        and text.count("STOCK_NUMERIC_READY probe=common_context_can_seq_rm") == 1
        and text.count("STOCK_NUMERIC_ROW") == 3,
        "stock coverage",
    )
    native = {}
    for sign, hits, misses, cpu in re.findall(
        r"llama_moe_cache: ubatch\s+(<=|>) 8: hits = (\d+), misses = (\d+) \((\d+) on the CPU\)",
        text,
    ):
        require(sign not in native and cpu == "0", "unexpected counter source")
        native[sign] = int(hits) + int(misses)
    require(native.keys() == {"<=", ">"}, "incomplete aggregation")
    difference = native[">"] - sum(by_layer)
    return dict(
        evidence="TRACE_DERIVED_FROM_MEASURED_C110",
        receipt_c294_sha256=PAIR_SHA,
        receipt_stock_sha256=STOCK_SHA,
        journal_sha256=on["numerical"]["routing"]["sha256"],
        stock_log_sha256=stock["raw_sha256"]["client.log"],
        large_logical_rows=35 * 16,
        c294_large_distinct_by_layer=by_layer,
        c294_large_distinct_sum=sum(by_layer),
        stock_large_distinct_sum=native[">"],
        large_delta_stock_minus_c294=difference,
        stock_only_layer_expert_pairs_at_least=max(0, difference),
        c294_small_distinct_by_supplied_call=small_calls,
        stock_small_distinct_sum=native["<="],
        stock_small_internal_probe_distinct=native["<="] - sum(small_calls),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("journal", "pair-receipt", "stock-log", "new-output"):
        p.add_argument("--" + opt, type=Path, required=True)
    args = p.parse_args()
    args.new_output.mkdir(exist_ok=False, mode=0o700)
    result = compare(args.journal, args.pair_receipt, args.stock_log)
    (args.new_output / ".pending").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    (args.new_output / ".pending").rename(args.new_output / "receipt.json")
