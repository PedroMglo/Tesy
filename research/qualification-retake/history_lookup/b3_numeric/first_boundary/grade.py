"""Strict OFF bridges, strided tensor geometry and bitwise first-observed frontier."""

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from schema import POSITIONS, population  # noqa: E402

OFF_FAMILY = "97ae7b5b9c9deed4e730fb1ddb50cdbd6d671aeea5169f73db2c96f49b40a7d9"
OFF_COMPACT = "7d95720e2f1a2ea35b9e037b2c4c0f9e93735ce692be6bd40c3aff75ca5b137c"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def old_rows():
    path = HERE.parent / "evidence/numeric.json"
    need(sha(path) == OFF_COMPACT, "historical control evidence")
    record = json.loads(path.read_bytes())
    need(record["raw_receipt_sha256"] == OFF_FAMILY, "OFF identity")
    return record["arms"]


def bridge(directory, mode):
    checked = {}
    for name, expected in old_rows()[mode]["files_observed"].items():
        path = directory / name
        need(path.is_file() and not path.is_symlink(), "missing OFF witness " + name)
        checked[name] = path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"]
    return {"bitwise": all(checked.values()), "witnesses": checked}


def historical(family):
    need(sha(family / "receipt.json") == OFF_FAMILY, "original OFF family")
    result = {}
    for mode in ("AR", "B3"):
        need(sha(family / mode / "receipt.json") == old_rows()[mode]["receipt_sha256"], "OFF arm")
        (capture,) = (family / mode / "raw").glob("*.capture")
        result[mode] = bridge(capture, mode)
        need(result[mode]["bitwise"], "archived OFF bytes")
    return result


def check_geometry(folder, mode, cuts):
    expected = {
        (pos, name) for pos in (POSITIONS if mode == "AR" else [189]) for _, name, _ in cuts
    }
    lookup = {name: s for _, name, s in cuts}
    seen = set()
    for line in (folder / "geometry.tsv").read_text().splitlines():
        f = line.split("\t")
        need(len(f) == 12, "geometry fields")
        start, n = map(int, f[:2])
        name, op = f[2:4]
        need((start, name) in expected - seen and n == (1 if mode == "AR" else 3), "unexpected cut")
        s = lookup[name]
        shape, pitch = tuple(map(int, f[4:8])), tuple(map(int, f[8:]))
        want = (*s.dims, n) + (1,) * (3 - len(s.dims))
        need(shape == want and op in s.ops, "cut shape or operation " + name)
        need(pitch[0] == 4 and pitch[1] >= s.dims[0] * 4, "row pitch")
        if len(s.dims) == 2 and n > 1:
            need(pitch[2] >= (s.dims[1] - 1) * pitch[1] + s.dims[0] * 4, "position pitch")
        seen.add((start, name))
    need(seen == expected, "missing synchronized cuts")


def validate_words(data, site):
    count = math.prod(site.dims)
    need(len(data) == count * 4, "cut payload length")
    if site.kind == "I32":
        ids = struct.unpack("<4i", data)
        need(len(set(ids)) == 4 and min(ids) >= 0 and max(ids) < 128, "logical ordered ranks")
    else:
        need(all(map(math.isfinite, struct.unpack(f"<{count}f", data))), "nonfinite activation")


def check_arm(capture, mode, cuts=None):
    cuts = list(population() if cuts is None else cuts)
    folder = capture / "boundary"
    check_geometry(folder, mode, cuts)
    inventory = {"geometry.tsv"}
    hashes = {}
    size = 0
    for _, name, site in cuts:
        for position in POSITIONS:
            filename = f"{position}.{name}.bin"
            inventory.add(filename)
            path = folder / filename
            need(path.is_file() and not path.is_symlink(), "cut file")
            data = path.read_bytes()
            validate_words(data, site)
            hashes[filename] = hashlib.sha256(data).hexdigest()
            size += len(data)
    need(inventory == {p.name for p in folder.iterdir()}, "unexpected boundary files")
    return dict(
        payloads=len(hashes),
        bytes=size,
        geometry_sha256=sha(folder / "geometry.tsv"),
        files_sha256=hashes,
    )


def word_diff(a, b):
    need(len(a) == len(b) and len(a) % 4 == 0, "paired row size")
    if a == b:
        return 0, None
    n = len(a) // 4
    count, first = 0, None
    for i, (x, y) in enumerate(
        zip(struct.unpack(f"<{n}I", a), struct.unpack(f"<{n}I", b), strict=True)
    ):
        if x != y:
            if first is None:
                first = i
            count += 1
    return count, first


def compare(ar, b3, cuts=None):
    cuts = list(population() if cuts is None else cuts)
    arms = [check_arm(folder, mode, cuts) for folder, mode in ((ar, "AR"), (b3, "B3"))]
    rows = []
    for layer, name, site in cuts:
        for position in POSITIONS:
            filename = f"{position}.{name}.bin"
            left, right = (x["files_sha256"][filename] for x in arms)
            changes, first = (0, None)
            if left != right:
                changes, first = word_diff(
                    (ar / "boundary" / filename).read_bytes(),
                    (b3 / "boundary" / filename).read_bytes(),
                )
                need(changes > 0, "changed cut after validation")
            rows.append(
                dict(
                    layer=layer,
                    site=site.name,
                    group=site.group,
                    position=position,
                    changed_words=changes,
                    first_changed_index=first,
                    words=math.prod(site.dims),
                    ar_sha256=left,
                    b3_sha256=right,
                )
            )

    def frontier(items):
        diff = [r for r in items if r["changed_words"]]
        if not diff:
            return None
        first = min((r["layer"], r["group"]) for r in diff)
        return [r for r in diff if (r["layer"], r["group"]) == first]

    return dict(
        status="DIFFERENT_AT_OBSERVED_CUT" if frontier(rows) else "EQUAL_THROUGH_OBSERVED_CUTS",
        first=frontier(rows),
        per_position={str(i): frontier(r for r in rows if r["position"] == i) for i in POSITIONS},
        comparisons=rows,
    )
