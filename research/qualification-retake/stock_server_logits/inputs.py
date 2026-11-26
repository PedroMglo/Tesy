"""Authenticate the private C110 token bundle and select the first 16 native IDs."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE.parent / "stock_numeric/reference-r1/receipt.json"
MANIFEST = HERE.parents[2] / "results/c110-decode-triangle-20260929T0900Z/manifest.json"
MANIFEST_SHA = "278c6a9f72ee3df42de03d67dc56079ec8444b2baab503fb5aa0f1268c442869"
REFERENCE_SHA = "3d6e18f7397ac97db30905ff291ddd96e7efb8b525e4cde515b551524f9f146a"
FIXTURE_SHA = "d406b5b1733afbd676efd318ee77d81938402bf7c40e49dc8ca131a24c240558"
PACKED_18_SHA = "80536eadb97029b88c1d54a06a0ffb2f693c2a10029631f10e59e86745d73479"
FIXTURE_NAME = "fixture_v2.ids.tsv"
VOCAB = 201088


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode_fixture(bundle):
    records = {}
    for line in bundle.decode("ascii").splitlines():
        key, value = line.split("\t", 1)
        require(key not in records, "duplicate C110 field")
        records[key] = value
    prompt = [int(x) for x in records["prompt"].split(",")]
    continuation = [int(x) for x in records["continuation192"].split(",")]
    require(len(prompt) == 2009 and len(continuation) == 192, "C110 token dimensions")
    require(all(0 <= x < VOCAB for x in prompt + continuation), "C110 ID range")
    return prompt[:16], struct.pack("<18i", *prompt[:16], *continuation[:2])


def load_prompt(c110_raw):
    manifest = MANIFEST.read_bytes()
    reference = REFERENCE.read_bytes()
    require(
        digest(manifest) == MANIFEST_SHA and digest(reference) == REFERENCE_SHA,
        "C110 manifest or packed-input receipt",
    )
    source = json.loads(manifest)["files"][FIXTURE_NAME]
    ref = json.loads(reference)
    require(
        source == {"bytes": 9994, "sha256": FIXTURE_SHA}
        and ref["status"] == "PASS_SIX_HISTORICAL_REFERENCES_ONLY"
        and ref["input_fixture_sha256"] == FIXTURE_SHA
        and ref["packed_18_ids_sha256"] == PACKED_18_SHA
        and ref["vocab"] == VOCAB,
        "C110 source or packed-input identity",
    )
    with (Path(c110_raw) / FIXTURE_NAME).open("rb") as f:
        bundle = f.read(source["bytes"] + 1)
    require(len(bundle) == source["bytes"] and digest(bundle) == FIXTURE_SHA, "C110 bundle")
    ids, packed = decode_fixture(bundle)
    require(digest(packed) == PACKED_18_SHA, "independent 16+2 packed IDs")
    return ids, {
        "c110_manifest_sha256": MANIFEST_SHA,
        "reference_receipt_sha256": REFERENCE_SHA,
        "fixture_sha256": FIXTURE_SHA,
        "fixture_bytes": len(bundle),
        "packed_18_ids_sha256": PACKED_18_SHA,
        "prompt_count": len(ids),
        "prompt_ids_sha256": digest(packed[: 16 * 4]),
        "vocab": VOCAB,
    }


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--c110-raw", required=True, type=Path)
    _, meta = load_prompt(args.parse_args().c110_raw)
    print(json.dumps(meta, sort_keys=True))
