"""Numerical gate for the isolated slots32 C110 16+2 diagnostic."""

import argparse
import csv
import hashlib
import json
import math
import runpy
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
C110 = REPO / "results/c110-decode-triangle-20260929T0900Z"
DIGEST = "1fb158e3fa6bd7ec2e48d4c85c1f0a79b8d3575e9ca58d8a696b5c3ea8f4e613"
IDS = "d406b5b1733afbd676efd318ee77d81938402bf7c40e49dc8ca131a24c240558"
MANIFEST = "278c6a9f72ee3df42de03d67dc56079ec8444b2baab503fb5aa0f1268c442869"
VOCAB = 201088
SIZE = 3 * VOCAB * 4


def require(value, message):
    if not value:
        raise ValueError(message)


def hashed(data):
    return hashlib.sha256(data).hexdigest()


def sealed(path, n, digest):
    require(path.stat().st_size == n, f"{path.name}: unexpected length")
    data = path.read_bytes()
    require(hashed(data) == digest, f"{path.name}: unexpected digest")
    return data


def reference(raw):
    manifest = (C110 / "manifest.json").read_bytes()
    require(hashed(manifest) == MANIFEST, "changed reference manifest")
    records = json.loads(manifest)["files"]
    for name, n, digest in [
        ("fixture_v2.ids.tsv", 9994, IDS),
        ("c110-canary-a.logits.f32", SIZE, DIGEST),
    ]:
        require(records[name] == {"bytes": n, "sha256": digest}, "invalid sealed reference")
    data = sealed(raw / "fixture_v2.ids.tsv", 9994, IDS)
    tsv = dict(line.split("\t", 1) for line in data.decode().splitlines())
    supplied = [int(x) for x in tsv["continuation192"].split(",")][:2]
    gold = sealed(raw / "c110-canary-a.logits.f32", SIZE, DIGEST)
    require(all(math.isfinite(f) for (f,) in struct.iter_unpack("<f", gold)), "nonfinite gold")
    return supplied, gold


def routes(data):
    journal = runpy.run_path(str(HERE.parent / "prefix_observer/journal.py"))
    counts = {"M": 0, "S": 0}
    actual = []
    cuts = []
    for event in journal["records"](data):
        if event[0] == "cut":
            cuts.append(event[1:])
        else:
            require(event[0] == "row", "unexpected pruned FFN in canary")
            _, call, ub, layer, pos, mode, _experts = event
            counts[mode] += 1
            actual.append((call, ub, layer, pos))
    expected = [
        (call, 1, layer, pos)
        for call, positions in [(1, list(range(16))), (2, [16]), (3, [17])]
        for layer in range(36)
        for pos in (positions if layer < 35 else positions[-1:])
    ]
    require(actual == expected and cuts == [("P", 1), ("I", 2)], "route boundary mismatch")
    return {"counts_by_path": counts, "groups": len(actual), "sha256": hashed(data)}


def numerical(raw_c110, prefix, mode):
    require(mode in {"OFF", "ON"}, "unknown observer mode")
    supplied, gold = reference(raw_c110)
    logits = sealed(Path(str(prefix) + ".logits.f32"), SIZE, DIGEST)
    require(logits == gold, "bitwise numerical mismatch")
    with Path(str(prefix) + ".steps.tsv").open() as stream:
        steps = list(csv.DictReader(stream, delimiter="\t"))
    require(
        [(int(r["step"]), int(r["position"]), int(r["token_id"])) for r in steps]
        == [(0, 16, supplied[0]), (1, 17, supplied[1])],
        "teacher-forced work mismatch",
    )
    require(
        all(
            math.isfinite(float(s["completion_s"])) and float(s["completion_s"]) > 0 for s in steps
        ),
        "invalid step time",
    )
    with Path(str(prefix) + ".ops.tsv").open() as stream:
        ops = list(csv.DictReader(stream, delimiter="\t"))
    require(
        len(ops) == 1
        and [ops[0][key] for key in ("arm", "prompt_tokens", "continuation_tokens", "logit_rows")]
        == ["C", "16", "2", "3"],
        "canary scope mismatch",
    )
    journal = Path(str(prefix) + ".routes.bin")
    routing = None
    if mode == "ON":
        require(0 < journal.stat().st_size <= 1024**2, "unbounded or empty journal")
        routing = routes(journal.read_bytes())
    else:
        require(not journal.exists(), "OFF emitted route journal")
    return {
        "status": "PASS_NUMERICAL_CANARY",
        "mode": mode,
        "logits_sha256": DIGEST,
        "logit_rows": 3,
        "vocab": VOCAB,
        "routing": routing,
    }


def compare_rows(raw, gold, vocab=VOCAB):
    """Describe a slots28 result without publishing model outputs or weakening bitwise equality."""
    require(len(raw) == len(gold) == 12 * vocab, "three full rows required")
    rows = []
    for row in range(3):
        a = raw[row * 4 * vocab : (row + 1) * 4 * vocab]
        b = gold[row * 4 * vocab : (row + 1) * 4 * vocab]
        different = sum(
            x != y
            for x, y in zip(struct.iter_unpack("<I", a), struct.iter_unpack("<I", b), strict=True)
        )
        actual = struct.unpack(f"<{vocab}f", a)
        expected = struct.unpack(f"<{vocab}f", b)
        finite = all(math.isfinite(x) for x in actual)
        rows.append(
            {
                "row": row,
                "sha256": hashed(a),
                "different_f32_bits_count": different,
                "all_finite": finite,
                "max_abs": max(abs(x - y) for x, y in zip(actual, expected, strict=True))
                if finite
                else None,
                "greedy_equal": max(range(vocab), key=actual.__getitem__)
                == max(range(vocab), key=expected.__getitem__)
                if finite
                else None,
            }
        )
    return {"sha256": hashed(raw), "rows": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-c110", required=True, type=Path)
    p.add_argument("--prefix", required=True, type=Path)
    p.add_argument("--mode", required=True, choices=["OFF", "ON"])
    args = p.parse_args()
    try:
        print(json.dumps(numerical(args.raw_c110, args.prefix, args.mode), sort_keys=True))
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(f"FAIL_NUMERICAL_CANARY {exc}") from exc
