"""Export both request clocks, deadline prices and arithmetic without storing trace rows."""

import argparse
import hashlib
import json
from pathlib import Path


def compact(data):
    r = json.loads(data)
    if r["status"] != "REPRODUCED_CONDITIONAL_POST_ATTENTION_WINDOWS":
        raise ValueError("expected completed deadline analysis")
    out = {k: v for k, v in r.items() if k not in ("P97", "P106")}
    out["full_receipt_sha256"] = hashlib.sha256(data).hexdigest()
    cols = (
        "wall_early_bytes_floor",
        "contracted_early_bytes_floor",
        "residual_extra_wall_floor_ns",
        "observed_margin_ns",
        "margin_at_6_ns",
        "margin_at_8_ns",
        "margin_at_10_ns",
        "min_decode_rate_for_both_outputs_per_s",
    )
    out["price_columns"] = cols
    for tag in ("P97", "P106"):
        old = r[tag]
        z = {k: v for k, v in old.items() if k != "banks"}
        z["banks"] = {}
        for name, b in old["banks"].items():
            prices = {}
            for w in b["windows"]:
                k = "/".join(map(str, (w["horizon"], w["release"], w["width"])))
                prices[k] = {"source_jobs": w["source_jobs"], "licensed_jobs": w["licensed_jobs"]}
                for point in w["limits"]:
                    fields = {**point, **point["costs"]}
                    prices[k][str(point["bytes_per_s"])] = [fields[c] for c in cols]
            z["banks"][name] = {**{k: v for k, v in b.items() if k != "windows"}, "prices": prices}
        out[tag] = z
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("first", "second", "new-output"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    data = a.first.read_bytes()
    if a.second.read_bytes() != data:
        raise ValueError("replication mismatch")
    with a.new_output.open("x") as f:
        json.dump(compact(data), f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
