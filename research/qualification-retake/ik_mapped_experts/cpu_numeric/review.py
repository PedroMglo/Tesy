"""Reopen the two short CPU trajectories and independently compare each entire F32 row."""

import argparse
import hashlib
import heapq
import json
import math
import struct
import sys
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[1]
VOCAB = 201088
WIDTH = 4 * VOCAB
STOCK_SHA = "df15a25bfec9c498bbb8bdaf111b14228912d85c1cd4ebb053784cf77bfa05ec"
REFERENCE_RECEIPT = "ebd19afb495957175eedc994a3fa35a069d17d135a3f82c14df62ac16e88715a"
IDS17 = "378eeb5ae41c80e16df38faad214c82e138727d2ddc1723a44f09c29c6e0f75c"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected, size=None):
    need(path.is_file() and not path.is_symlink(), "regular file required: " + path.name)
    length = path.stat().st_size
    need(0 < length <= 8 * 1024**2 and (size is None or length == size), "size: " + path.name)
    data = path.read_bytes()
    need(len(data) == length and digest(data) == expected, "digest: " + path.name)
    return data


def describe(data, vocab=VOCAB):
    values = struct.unpack(f"<{vocab}f", data)
    finite = all(map(math.isfinite, values))
    top = heapq.nsmallest(5, range(vocab), key=lambda i: (-values[i], i)) if finite else []
    return dict(
        sha256=digest(data),
        bytes=len(data),
        finite=finite,
        top5=top,
        max_ties=values.count(values[top[0]]) if finite else None,
        nonfinite=sum(not math.isfinite(v) for v in values),
    )


def references(raw_parent, stock_file):
    c110 = run_path(str(QUAL / "stock_numeric/evaluate.py"))
    ids, historical, labels = c110["inputs"](raw_parent)
    need(digest(ids[:68]) == IDS17 and struct.unpack_from("<i", ids, 64)[0] == 976, "teacher")
    stock_report = json.loads(
        pinned(QUAL / "stock_numeric/physical-r1/receipt.json", REFERENCE_RECEIPT)
    )
    need(
        stock_report["scope"] == "SUPPLIED_C110_16_1_1"
        and stock_report["child_gone"]
        and stock_report["input_sha256"] == digest(ids)
        and stock_report["raw_sha256"]["candidate.logits.f32"] == STOCK_SHA,
        "stock authority",
    )
    stock = pinned(stock_file, STOCK_SHA, 3 * WIDTH)
    papers = {"C110": historical, "stock_e95426f": stock}
    refs = {
        name: {p: data[(p - 15) * WIDTH : (p - 14) * WIDTH] for p in (15, 16)}
        for name, data in papers.items()
    }
    for p in (15, 16):
        need(
            digest(refs["stock_e95426f"][p]) == stock_report["rows"][p - 15]["sha256"], "stock row"
        )
        for rows in refs.values():
            desc = describe(rows[p])
            need(
                desc["finite"]
                and desc["max_ties"] == 1
                and desc["top5"][0] == (3659 if p == 15 else 3992),
                "reference rank",
            )
    return refs, labels


def candidate(label, directory, sha):
    r = json.loads(pinned(directory / "receipt.json", sha))
    need(r["arm"] == label, "wrong arm")
    base = directory / "capture"
    need(not base.is_symlink(), "linked capture directory")
    rows = {}
    for p in (15, 16):
        n = f"pos{p}.f32"
        if n in r["logits_sha256"]:
            rows[p] = pinned(base / n, r["logits_sha256"][n], WIDTH)
    if r["status"] == "PASS_IK_CPU_NUMERIC_ARM":
        need(set(rows) == {15, 16}, "successful arm missing a cut")
    else:
        need(r["status"].startswith("FAIL"), "arm is not terminal")
    return rows, r["status"]


def review(args):
    sys.path.insert(0, str(QUAL / "stock_server_logits"))
    summarize = run_path(str(QUAL / "stock_server_logits/compare.py"))["summarize"]
    refs, labels = references(args.c110_parent, args.stock_rows)
    arms = args.arm or []
    need([a[0] for a in arms] in ([], ["D0"], ["D0", "D1"]), "expected references, D0, or D0/D1")
    result = {
        "status": "PASS_REFERENCES_ONLY",
        "teacher_id": 976,
        "c110_verified_arms": labels,
        "reference_rows": {
            name: {p: describe(row) for p, row in rows.items()} for name, rows in refs.items()
        },
        "baseline_contrast": {
            p: summarize(refs["C110"][p], refs["stock_e95426f"][p]) for p in (15, 16)
        },
        "arms": {},
        "prefetch_contrast": {},
    }
    control = {}
    for label, directory, sha in arms:
        rows, status = candidate(label, Path(directory), sha)
        row_details = {p: describe(row) for p, row in rows.items()}
        result["arms"][label] = dict(
            terminal_sha256=sha,
            terminal_status=status,
            rows=row_details,
            against_reference={
                name: {p: summarize(refrows[p], row) for p, row in rows.items()}
                for name, refrows in refs.items()
            },
        )
        if label == "D0":
            control = rows
            result["status"] = "PASS_D0_TWO_GREEDY_CUTS"
        else:
            need(result["status"] == "PASS_D0_TWO_GREEDY_CUTS", "D1 after failed D0")
            diff = {p: summarize(control[p], row) for p, row in rows.items()}
            result["prefetch_contrast"] = diff
            result["status"] = (
                "PASS_D0_D1_TWO_BITWISE_ROWS"
                if all(x["bitwise_equal"] for x in diff.values())
                else "FAIL_PREFETCH_BITWISE"
            )
        if status != "PASS_IK_CPU_NUMERIC_ARM":
            result["status"] = "FAIL_PHYSICAL_ARM"
        elif any(
            not x["finite"] or x["max_ties"] != 1 or x["top5"][0] != (3659 if p == 15 else 3992)
            for p, x in row_details.items()
        ):
            result["status"] = "FAIL_FINITE_OR_GREEDY_GATE"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c110-parent", type=Path, required=True)
    parser.add_argument("--stock-rows", type=Path, required=True)
    parser.add_argument("--arm", action="append", nargs=3, metavar=("ARM", "DIR", "RECEIPT_SHA"))
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.new_output_dir
    out.mkdir(mode=0o700, exist_ok=False)
    try:
        result = review(args)
    except Exception as error:
        result = {"status": "FAIL_REVIEW", "error": str(error)}
    with (out / "receipt.json").open("x") as sink:
        json.dump(result, sink, indent=2, sort_keys=True, allow_nan=False)
        sink.write("\n")
    print(result["status"])
    raise SystemExit(0 if result["status"].startswith("PASS") else 1)
