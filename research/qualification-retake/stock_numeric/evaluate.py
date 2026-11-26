"""Seal C110 inputs and compare three full stock logit vectors without loading a model."""

import argparse
import hashlib
import heapq
import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "nvme_prefix_gate"))
from gate import (  # noqa: E402
    C110,
    DIGEST,
    IDS,
    REPO,
    SIZE,
    VOCAB,
    compare_rows,
    reference,
    require,
    sealed,
)

C109 = REPO / "results/c109-decode-triangle-20260929T0815Z"


def dump(out, data):
    pending = out / ".receipt.pending"
    pending.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    pending.rename(out / "receipt.json")


def inputs(raw_parent):
    directory = raw_parent / C110.name / "raw"
    continuation, gold = reference(directory)
    full = sealed(directory / "fixture_v2.ids.tsv", 9994, IDS)
    fields = dict(line.split("\t", 1) for line in full.decode().splitlines())
    prompt = [int(t) for t in fields["prompt"].split(",")]
    require(len(prompt) == 2009 and len(continuation) == 2, "prompt/continuation dimensions")
    ids = prompt[:16] + continuation
    require(all(0 <= t < VOCAB for t in ids), "out of vocabulary")
    arms = []
    for source, prefix in ((C109, "c109"), (C110, "c110")):
        manifest = json.loads((source / "manifest.json").read_text())["files"]
        for arm in "abc":
            name = f"{prefix}-canary-{arm}.logits.f32"
            require(manifest[name] == {"bytes": SIZE, "sha256": DIGEST}, "source manifest")
            require(
                sealed(raw_parent / source.name / "raw" / name, SIZE, DIGEST) == gold,
                "reference disagreement",
            )
            arms.append(f"{prefix}-{arm}")
    return struct.pack("<18i", *ids), gold, arms


def compare(candidate, gold, vocab=VOCAB):
    summary = compare_rows(candidate, gold, vocab=vocab)
    nonfinite = False
    for i, row in enumerate(summary["rows"]):
        size = 4 * vocab
        a = struct.unpack_from(f"<{vocab}f", candidate, i * size)
        b = struct.unpack_from(f"<{vocab}f", gold, i * size)
        require(all(math.isfinite(v) for v in b), "invalid reference")
        row.update(
            position=(15, 16, 17)[i],
            nan=sum(math.isnan(v) for v in a),
            pos_inf=a.count(math.inf),
            neg_inf=a.count(-math.inf),
        )

        def top(values):
            return heapq.nsmallest(5, range(vocab), key=lambda idx: (-values[idx], idx))

        row["expected_top_ids"] = top(b)
        row["stock_top_ids"] = None
        row["mean_abs"] = None
        row["rmse"] = None
        if row["all_finite"]:
            row["stock_top_ids"] = top(a)
            row["mean_abs"] = math.fsum(abs(x - y) for x, y in zip(a, b, strict=True)) / vocab
            row["rmse"] = math.sqrt(
                math.fsum((x - y) ** 2 for x, y in zip(a, b, strict=True)) / vocab
            )
        else:
            nonfinite = True
    status = "FAIL_NONFINITE" if nonfinite else "FINITE_DIFFERENT_BITS_PARITY_INCONCLUSIVE"
    if candidate == gold and not nonfinite:
        status = "PASS_BITWISE_3_ROWS"
    return {"status": status, **summary}


def run(args):
    args.new_output.mkdir(exist_ok=False, mode=0o700)
    r = {
        "status": "FAIL",
        "protocol_sha256": hashlib.sha256((HERE / "protocol.md").read_bytes()).hexdigest(),
    }
    try:
        packed, gold, arms = inputs(args.raw_parent)
        r.update(
            historical_arms=arms,
            gold_sha256=DIGEST,
            input_fixture_sha256=IDS,
            packed_18_ids_sha256=hashlib.sha256(packed).hexdigest(),
            vocab=VOCAB,
            gold_bytes=len(gold),
        )
        if args.new_input is not None:
            with args.new_input.open("xb") as f:
                f.write(packed)
        if args.candidate is None:
            r.update(status="PASS_SIX_HISTORICAL_REFERENCES_ONLY", candidate="NOT_RUN")
        else:
            require(args.candidate.stat().st_size == SIZE, "incomplete candidate")
            r.update(compare(args.candidate.read_bytes(), gold))
    except Exception as exc:
        r["reason"] = str(exc)
    dump(args.new_output, r)
    return r["status"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-parent", type=Path, required=True)
    p.add_argument("--new-output", type=Path, required=True)
    p.add_argument("--new-input", type=Path, help="Private 72-byte target input in a new file")
    p.add_argument("--candidate", type=Path)
    status = run(p.parse_args())
    print(status)
    sys.exit(0 if status.startswith("PASS") else 1)
