"""Verify independent receipts and export all margins without the per-phase work arrays."""

import argparse
import hashlib
import json
from pathlib import Path


def compact(first, second):
    data = first.read_bytes()
    if data != second.read_bytes():
        raise ValueError("different reproductions")
    r = json.loads(data)
    if r["status"] != "REPRODUCED_ALL_PREFILL_DELIVERIES":
        raise ValueError("full audit has no quantified result")
    out = {k: v for k, v in r.items() if k not in ("P97", "P106")}
    out["full_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    out["margin_columns_ns"] = [
        "priced_first",
        "priced_decode",
        "free_first",
        "free_decode",
        "only_prefill_changed_priced_first",
        "only_prefill_changed_priced_decode",
    ]
    for tag in ("P97", "P106"):
        item = r[tag]
        out[tag] = {k: v for k, v in item.items() if k != "modes"}
        out[tag]["modes"] = {}
        for name, mode in item["modes"].items():
            margins = {
                k: v["priced_set_margins_ns"]
                + v["free_set_margins_ns"]
                + v["same_previous_decode_priced_set_margins_ns"]
                for k, v in mode["scenarios"].items()
            }
            out[tag]["modes"][name] = dict(
                deliveries=mode["deliveries"], storage=mode["storage"], margins_ns=margins
            )
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "second", "new-output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    report = compact(a.first, a.second)
    with a.new_output.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
