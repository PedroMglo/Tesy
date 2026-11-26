"""Intersect AR callback coverage with the callbacks still charged by a serial L25 suffix."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SER = run_path(str(HERE.parent / "score.py"))
BANK = run_path(str(HERE.parents[2] / "prefill_retention/request_cost/score.py"))
check, digest, pinned = SER["check"], SER["digest"], SER["pinned"]
H = {
    "protocol": "d7f82141982c18f4cda5165ae69902df8d28ce12d1558a2acfe6065e985791c3",
    "serial_code": "c8b63224facd06ae49e08cbb20c0ea19a98c77aa0354e51a48cf9349e42d776e",
    "bank_code": "bdd8a06f8694efccbd5282db0b73b222768d328f8263e431c694dcbadddb991c",
    "serial_receipt": "2b1f7f3111cd5442d0177546ccbbff9180ca1e3a10067b056d6d399631201561",
    "bank_receipt": "8c7d2c73abbe81bf3214f3f79cb7fd30fb21ec6c85078e93c42701730dbe0299",
}
MODES = ("direct", "drained_retained_origins", "drained", "persistent")
PHASES = ("prefill", "decode_first", "decode_tail")


def serialized(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def census(waves, actions, bank):
    totals = defaultdict(Counter)
    modes = {m: {p: Counter() for p in PHASES} for m in MODES}
    active = {m: False for m in MODES}
    witness = hashlib.sha256()
    for w in waves:
        call, tile, layer, wave = w.site
        stage = BANK["phase"](call)
        is_verified = actions[call - 1] in ("anchor", "skip")
        retained = not is_verified or layer >= 25
        tier = "CPU" if layer < 25 else "CUDA0"
        part = stage + "/" + ("verified" if is_verified else "ordinary") + "/" + tier
        row = totals[part]
        hits = {k for k in w.reserved if BANK["expert"](k) in bank}
        width = w.end - w.start
        check(width >= 0, "callback length")
        row["callbacks"] += 1
        row["width_ns"] += width
        row["reserved"] += len(w.reserved)
        row["hits"] += len(hits)
        row["retained_callbacks"] += int(retained)
        row["retained_ns"] += width * retained
        row["retained_hit_jobs"] += len(hits) * retained
        floor = BANK["RELEASE"]["four_lanes"](
            [v for k, v in w.required_service.items() if k not in hits]
        )
        check(0 <= floor <= width, "four-worker floor")
        flags = []
        for m in MODES:
            drain = m.startswith("drained")
            if drain and w.start_drained:
                active[m] = False
            origin = bool(hits) and (retained or m != "drained_retained_origins")
            covered = bool(hits) if m == "direct" else active[m] or origin
            s = modes[m][stage]
            if covered:
                s["gross_covered_ns"] += width
                if retained:
                    field = "direct" if hits else "propagated"
                    s[field + "_ns"] += width
                    s[field + "_callbacks"] += 1
                    s["retained_covered_ns"] += width
                    s["retained_floor_1x_ns"] += floor
                    s["retained_floor_half_ns"] += floor // 2
                else:
                    s["overlap_already_free_ns"] += width
            if m != "direct":
                active[m] = covered and not (drain and w.end_drained)
            flags.append(int(covered))
        fields = (call, tile, layer, wave, w.start, w.end, int(retained), len(hits), floor, *flags)
        witness.update((",".join(map(str, fields)) + "\n").encode())
    for table in modes.values():
        for z in table.values():
            check(
                z["gross_covered_ns"] == z["overlap_already_free_ns"] + z["retained_covered_ns"]
                and z["direct_ns"] + z["propagated_ns"] == z["retained_covered_ns"],
                "non-disjoint credits",
            )
    return totals, modes, witness.hexdigest()


def price(suffix, prompt, phases):
    r = {}
    for label, field in (
        ("free", None),
        ("half", "retained_floor_half_ns"),
        ("1x", "retained_floor_1x_ns"),
    ):
        gain = {p: z["retained_covered_ns"] - (z[field] if field else 0) for p, z in phases.items()}
        first = suffix["first"]
        dec = suffix["decode"]
        first_floor = (
            first["fractions"]["0"]["projected_ns"] - gain["prefill"] - gain["decode_first"]
        )
        dec_floor = (
            dec["fractions"]["0"]["projected_ns"] - gain["decode_first"] - gain["decode_tail"]
        )
        prompt_floor = prompt - gain["prefill"]
        check(min(first_floor, dec_floor, prompt_floor) >= 0, "credit exceeds observed budget")
        fa = first["target_ns"] - first_floor
        da = dec["target_ns"] - dec_floor
        r[label] = dict(
            prefill_ns=prompt_floor,
            decode_ns=dec_floor,
            first_final_ns=first_floor,
            bank_gain_ns=gain,
            first_new_cost_budget_ns=fa,
            decode_new_cost_budget_ns=da,
            uniform_extra_per_attempt_ns=min(fa // first["attempts"], da // dec["attempts"]),
            joint="HEADROOM_ONLY" if min(fa, da) >= 0 else "NO_GO_FIXED_SCENARIO",
        )
    return r


def score_request(root, receipt, rows, banks, bank_ref, serial_ref):
    host = BANK["NATIVE"]["host_trace"](rows)
    actions = SER["LOOKUP"]["partition"](root / "ON", receipt)
    w, jobs = BANK["timeline"](rows)
    spans = SER["T"]["intervals"](rows, host["callback_spans"])
    check([(v.site[0], v.site[2], v.start, v.end) for v in w] == spans, "wave identity or ordering")
    serial_rows = SER["decompose"](host["calls"], actions, spans)
    raw = json.loads((root / "ON/raw/T2-result.json").read_bytes())
    prompt = int(Decimal(str(raw["timings"]["prompt_ms"])) * 10**6)
    check(
        abs(receipt["rows"][1]["prefill_s"] * 10**9 - prompt) < 2
        and len(w) == 2987
        and len(jobs) == 2354,
        "native prompt clock or lineage",
    )
    result = {}
    for name, keys in {"empty": set(), **banks, "all_jobs": set(map(BANK["expert"], jobs))}.items():
        counts, modes, witness = census(w, actions, keys)
        passes = {}
        for mode, phases in modes.items():
            if mode in ("drained", "persistent"):
                for p, z in phases.items():
                    check(
                        z["gross_covered_ns"]
                        == bank_ref["policies"][name][mode]["phases"][p]["callback_ns"],
                        "whole-request bank marginal disagrees",
                    )
            for p, z in phases.items():
                check(
                    z["retained_covered_ns"] <= modes["persistent"][p]["retained_covered_ns"],
                    "persistent credit",
                )
            passes[mode] = {}
            for tag, keep in (("suffix_to_return", True), ("suffix_callbacks_only", False)):
                serial = serial_ref[tag]
                check(
                    SER["price"](serial_rows[:46], bank_ref["first_final_ns"], 10**10, keep)
                    == serial["first"]
                    and SER["price"](serial_rows[2:], bank_ref["decode_ns"], BANK["ALLOW"], keep)
                    == serial["decode"],
                    "serial marginal",
                )
                passes[mode][tag] = price(serial, prompt, phases)
        result[name] = {
            "counts": counts,
            "influence": modes,
            "prices": passes,
            "wave_table_sha256": witness,
        }
    return {
        "prefill_ns": prompt,
        "first_final_ns": bank_ref["first_final_ns"],
        "decode_ns": bank_ref["decode_ns"],
        "actions": Counter(actions),
        "first_actions": Counter(actions[:46]),
        "banks": result,
        "pre_stream_diagnostic_allowance_ns": bank_ref["pre_stream_allowance_ns"],
        "actual_tail_callback_credit_ns": bank_ref["policies"]["all_jobs"]["persistent"][
            "client_tail_extra_ns"
        ],
    }


def run(archive):
    check(
        digest(HERE / "protocol.md") == H["protocol"]
        and digest(HERE.parent / "score.py") == H["serial_code"]
        and digest(Path(BANK["__file__"])) == H["bank_code"],
        "methods",
    )
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in BANK["SOURCES"].items()}
    serial = SER["assess"](roots["P97"], roots["P106"])
    bank = BANK["compare"](archive)
    for k, obj in (("serial_receipt", serial), ("bank_receipt", bank)):
        check(hashlib.sha256(serialized(obj)).hexdigest() == H[k], "full marginal receipt " + k)
    new = roots["P106"]
    sel, new_rows, _, _ = BANK["Q"]["read_new"](new, BANK["SOURCES"]["P106"][1])
    banks = {k: set(map(tuple, v["ordered_keys"])) for k, v in sel["banks"].items()}
    fam = pinned(new / "family.json", BANK["SOURCES"]["P106"][1])
    arm = pinned(new / "ON/arm.json", fam["arms"]["ON"]["sha256"])
    receipt = pinned(new / "ON/receipt.json", arm["receipt_sha256"])
    out = {
        "sources": H,
        "code_sha256": digest(Path(__file__)),
        "provenance": bank["provenance"],
        "status": "REPRODUCED_UNION_AT_FIXED_AR_PRICES",
    }
    out["P106"] = score_request(new, receipt, new_rows, banks, bank["P106"], serial["P106"])
    del new_rows
    old = roots["P97"]
    _, _, receipt, _ = BANK["CHAIN"]["chain"](old, BANK["Q"]["P97"])
    rows, _ = BANK["T"]["PFJ"]["read_journal"](old / "ON/raw/events.pfj")
    out["P97"] = score_request(old, receipt, rows, banks, bank["P97"], serial["P97"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        record = run(a.archive)
    except Exception as exc:
        record = {"status": "FAIL_PRESERVED", "reason": str(exc), "error_type": type(exc).__name__}
    (a.new_output_dir / "receipt.json").write_bytes(serialized(record))
    print(record["status"])
    raise SystemExit(int(record["status"] == "FAIL_PRESERVED"))
