"""Locate serialized KV differences in the closed C269 AR/B3 family, without inference."""

import argparse
import hashlib
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

FAMILY = "97ae7b5b9c9deed4e730fb1ddb50cdbd6d671aeea5169f73db2c96f49b40a7d9"
PROTOCOL = "c5ac242c84875f94848339b4af89952375ec2f43727dce8b6f32a57e3d1cabc2"
SOURCES = {
    "src/llama-context.cpp": "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
    "src/llama-kv-cache.cpp": "8db6426600c87a54967ef8c5074fd42ea768c2f97e90184749320adf19143ed7",
    "src/llama-kv-cache-iswa.cpp": (
        "c8f2cfa6a639be22dcd4e574ec70d6d2ab945a2f2e3d644cb000f5e202c6e0af"
    ),
    "src/llama-hparams.cpp": "b517fc2a9f56475bd66317e309ff56d4f816feb050e6c2dca08a81874a6d622b",
    "src/llama-hparams.h": "b200dc2ebcf776d30c8fe87a883b6b572f55d72cd8b0f9fc1ddeb5cbbd8bbe0e",
    "src/llama-model.cpp": "7af9ef3bb6dc9491f7280b3dbcc4f6605da7739b4288e7bee51881772f58f010",
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
    "ggml/include/ggml.h": "98c5fcf96279e16c09d42dcba482be1b03434839db723bba4b65518e424ba181",
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def pinned(path, digest):
    need(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 32 << 20,
        "input type or size",
    )
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == digest, "checksum " + path.name)
    return data


def layers_from_log(data):
    log = data.decode()
    sections = re.split(
        r"^llama_kv_cache_iswa: creating +(non-SWA|SWA) KV cache, size = 8192 cells$",
        log,
        flags=re.M,
    )
    need(len(sections) == 5 and sections[1::2] == ["non-SWA", "SWA"], "cache construction")
    banks = []
    for section, parity in zip(sections[2::2], [1, 0], strict=True):
        entries = re.findall(
            r"^llama_kv_cache: layer +(\d+): (dev = (?:CPU|CUDA0)|filtered)$", section, re.M
        )
        need([int(n) for n, _ in entries] == list(range(36)), "layer coverage/order")
        active = [int(n) for n, descriptor in entries if descriptor != "filtered"]
        need(active == list(range(parity, 36, 2)), "active layers")
        banks.append(active)
    return banks


def parse(blob, count, banks):
    offset = 0
    rows = {}
    expected = []

    def header(fmt, values):
        nonlocal offset
        fields = struct.Struct("<" + fmt)
        need(fields.unpack_from(blob, offset) == values, f"header at {offset}")
        expected.append((offset, fields.size))
        offset += fields.size

    header("II", (0xAF143CD8, 0))
    for bank, layers in zip(("base", "swa"), banks, strict=True):
        positions = range(0 if bank == "base" else count - 128, count)
        header("II", (1, len(positions)))
        for pos in positions:
            header("iIi", (pos, 1, 0))
        header("II", (0, len(layers)))
        for kind in ("K", "V"):
            for layer in layers:
                header("iQ", (1, 1024))
                for pos in positions:
                    rows[(bank, kind, layer, pos)] = offset
                    offset += 1024
    need(offset == len(blob), "EOF")
    return rows, expected


def compare(first, second, overlap=False):
    left, one = first
    right, two = second
    common = one.keys() & two.keys()
    need(overlap or one.keys() == two.keys(), "row lookup coverage")
    totals = Counter()
    grouped = defaultdict(Counter)
    by_position = Counter()
    changed_layers = set()
    first_file = None
    first_layer = None
    for key in sorted(common, key=one.__getitem__):
        bank, kind, layer, pos = key
        left_offset, right_offset = one[key], two[key]
        a, b = left[left_offset : left_offset + 1024], right[right_offset : right_offset + 1024]
        totals["compared_rows"] += 1
        if a == b:
            continue
        totals["differing_rows"] += 1
        changed_layers.add(layer)
        for index, (x, y) in enumerate(
            zip(struct.unpack("<512H", a), struct.unpack("<512H", b), strict=True)
        ):
            if x == y:
                continue
            if first_file is None or first_layer is None or layer < first_layer["layer"]:
                desc = dict(
                    bank=bank,
                    layer=layer,
                    kind=kind,
                    pos=pos,
                    index=index,
                    byte_offset=left_offset + 2 * index + ((x ^ y) & 255 == 0),
                )
                if first_file is None:
                    first_file = desc
                if first_layer is None or layer < first_layer["layer"]:
                    first_layer = desc
            sign_only_zero = (x & 0x7FFF) == 0 and (y & 0x7FFF) == 0
            nonfinite = ((x & 0x7C00) == 0x7C00) or ((y & 0x7C00) == 0x7C00)
            category = (
                "nonfinite_in_pair"
                if nonfinite
                else "zero_sign"
                if sign_only_zero
                else "unequal_finite"
            )
            grouped[f"{bank}_{kind}_{'prefix' if pos < 189 else 'new'}"][category] += 1
            by_position[pos] += 1
            totals[category] += 1
            totals["differing_words"] += 1
    return dict(
        totals=totals,
        by_bank_kind_positions=grouped,
        by_position=by_position,
        layers=sorted(changed_layers),
        first_file=first_file,
        lowest_layer_example=first_layer,
    )


def evaluate(family_dir, backend):
    pinned(Path(__file__).with_name("protocol.md"), PROTOCOL)
    for path, digest in SOURCES.items():
        pinned(backend / path, digest)
    family = json.loads(pinned(family_dir / "receipt.json", FAMILY))
    parsed = {}
    receipts = {}
    for arm in ("AR", "B3"):
        folder = family_dir / arm
        receipt = json.loads(pinned(folder / "receipt.json", family["arms"][arm]["receipt_sha256"]))
        need(receipt["status"] == "PASS_NUMERIC_ARM_" + arm, "arm status")
        unit = receipt["unit"]
        need(unit == Path(unit).name, "identity")
        raw = folder / "raw"
        monitor = json.loads(pinned(raw / (unit + ".json"), receipt["monitor_sha256"]))
        banks = layers_from_log(
            pinned(raw / (unit + ".stderr"), monitor["output_sha256"][".stderr"])
        )
        states = receipt["grade"]["states"]
        receipts[arm] = {}
        for name, count in (("initial-kv.bin", 189), ("post3-kv.bin", 192)):
            blob = pinned(raw / (unit + ".capture") / name, states[name]["sha256"])
            need(len(blob) == states[name]["bytes"], "snapshot size")
            rows, meta = parse(blob, count, banks)
            parsed[(arm, count)] = (blob, rows, meta)
            receipts[arm][name] = states[name]
    comparisons = {}
    for n in (189, 192):
        a, b = parsed["AR", n], parsed["B3", n]
        need(
            a[2] == b[2] and all(a[0][p : p + s] == b[0][p : p + s] for p, s in a[2]),
            "metadata mismatch",
        )
        comparisons[str(n)] = compare(a[:2], b[:2])
        comparisons[str(n)]["identical_metadata_bytes"] = sum(s for _, s in a[2])
    need(parsed["AR", 189][0] == parsed["B3", 189][0], "entry state")
    need(comparisons["192"]["totals"]["differing_words"] > 0, "closed difference not located")
    return dict(
        status="LOCATED_SERIALIZED_F16_DIFFERENCES",
        family_sha256=FAMILY,
        protocol_sha256=PROTOCOL,
        source_sha256=SOURCES,
        inputs=receipts,
        cuts=comparisons,
        retained_positions_from_entry={
            arm: compare(parsed[arm, 189][:2], parsed[arm, 192][:2], overlap=True)
            for arm in receipts
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "backend", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = evaluate(args.family, args.backend)
        rc = 0
    except (OSError, ValueError, KeyError, struct.error) as exc:
        report = dict(status="INCONCLUSIVE", reason=str(exc))
        rc = 1
    with (args.new_output_dir / "receipt.json").open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
