"""Reopen two synchronized KV snapshots using the C269 sequence writer and observed layer maps."""

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

PIN = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
FILES = {
    "src/llama-context.cpp": "7d8cfa9f33f38d761cf18b8e548ab7811866fbb8fdfaa95eeb2211d56851681b",
    "src/llama-kv-cache.cpp": "8db6426600c87a54967ef8c5074fd42ea768c2f97e90184749320adf19143ed7",
    "src/llama-kv-cache-iswa.cpp": "c8f2cfa6a639be22dcd4e574ec70d6d2ab945a2f2e3d644cb000f5e202c6e0af",
    "src/llama-hparams.h": "b200dc2ebcf776d30c8fe87a883b6b572f55d72cd8b0f9fc1ddeb5cbbd8bbe0e",
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
    "ggml/include/ggml.h": "98c5fcf96279e16c09d42dcba482be1b03434839db723bba4b65518e424ba181",
}
FAMILY = "27b97866f3d452786860f42133ffb247a9f06d95c904473aa2b09533de16c086"
AR = "9f4f7d6006cac1befa989df086af85a193778d8e5cae26775114b2ad66532fac"
LOGS = {
    "AR": "28a4bb6f0a7499b60a2f9599ee6d8358b7da6b283caeef776fd7045f9cc6dbac",
    "OFF": "65696e72dbc6dbf544360a8cdcf35460c4cbac3aee021a54003618a8b3bf7cb0",
    "ON": "8fe66a27943cd9759b838b6508394107b9683c33588e791a00c0f026b385f246",
}
GROUPS = (tuple(range(1, 36, 2)), tuple(range(0, 36, 2)))
MAGIC = 0xAF143CD8


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def parse(data, count, groups=GROUPS, swa=128, width=512):
    view = memoryview(data)
    offset = 0

    def take(n):
        nonlocal offset
        need(n >= 0 and offset + n <= len(view), "truncated KV")
        begin = offset
        offset += n
        return view[begin:offset]

    def unpack(fmt):
        return struct.unpack("<" + fmt, take(struct.calcsize("<" + fmt)))

    need(unpack("Ii") == (MAGIC, 0), "sequence header")
    out = {}
    formats = []
    for idx, layers in enumerate(groups):
        positions = range(count) if idx == 0 else range(max(0, count - swa), count)
        need(unpack("II") == (1, len(positions)), "stream or positions")
        cells = []
        for _ in positions:
            pos, ids, seq = unpack("iIi")
            need(ids == 1 and seq == 0, "owner of cell")
            cells.append(pos)
        need(sorted(cells) == list(positions), "missing or duplicated cell position")
        vtrans, nlayers = unpack("II")
        need(vtrans in (0, 1) and nlayers == len(layers), "layout or layer population")
        formats.append({"cell_count": len(cells), "v_trans": vtrans, "layers": nlayers})
        for role in ("K", "V"):
            for layer in layers:
                need(unpack("i") == (1,), "stored GGML type")
                if role == "V" and vtrans:
                    need(unpack("II") == (2, width), "transposed V shape")
                    matrix = take(2 * width * len(cells))
                    # Each consecutive pair stores a half. In dimension-major V, cells vary first.
                    for j, pos in enumerate(cells):
                        row = bytearray(2 * width)
                        for k in (0, 1):
                            row[k::2] = matrix[2 * j + k :: 2 * len(cells)]
                        out[layer, role, pos] = bytes(row)
                else:
                    need(unpack("Q") == (2 * width,), "KV row pitch")
                    for pos in cells:
                        out[layer, role, pos] = take(2 * width)
    need(offset == len(data), "trailing KV bytes")
    return out, formats


def source_and_log(log):
    matches = re.findall(
        r"^llama_kv_cache: layer\s+(\d+): (filtered|dev = (?:CPU|CUDA0))$", log, re.M
    )
    need(len(matches) == 72, "layer filter census")
    for k, layers in enumerate(GROUPS):
        group = matches[k * 36 : (k + 1) * 36]
        need(
            [int(n) for n, _ in group] == list(range(36))
            and [int(n) for n, v in group if v != "filtered"] == list(layers),
            "layer serialization order",
        )
    for label, value in (
        ("n_swa", 128),
        ("n_embd_head_k", 64),
        ("n_embd_head_v", 64),
        ("n_head_kv", 8),
    ):
        need(
            re.search(r"^print_info: " + label + r"\s+= " + str(value) + r"$", log, re.M),
            "KV geometry",
        )
    need(
        len(re.findall(r"18 layers,  1/1 seqs\), K \(f16\): .* V \(f16\):", log)) == 2,
        "typed K/V inventory",
    )


def load_arm(family, mode, expected):
    root = family / mode
    arm_path = root / "receipt.json"
    need(sha(arm_path) == expected, "arm receipt hash")
    arm = read(arm_path)
    raw = root / "raw"
    unit = arm["unit"]
    need(Path(unit).name == unit and arm["model_launch_receipts"] == 1, "unique arm")
    log = raw / (unit + ".stderr")
    need(sha(log) == LOGS[mode], "log identity")
    source_and_log(log.read_text())
    cap = raw / (unit + ".capture")
    need(sha(cap / "native.json") == arm["grade"]["native_sha256"], "native receipt")
    if mode == "AR":
        hashes = arm["coverage"]["files_sha256"]
    else:
        comparison = root / "comparison.json"
        need(sha(comparison) == arm["comparison_sha256"], "cut inventory")
        hashes = read(comparison)["coverage"]["files_sha256"]
    parsed = []
    files = {}
    for name, count in (("initial-kv.bin", 189), ("post3-kv.bin", 192)):
        p = cap / name
        h = sha(p)
        size = p.stat().st_size
        need(arm["grade"]["states"][name] == {"bytes": size, "sha256": h}, "KV receipt reference")
        body = p.read_bytes()
        data, formats = parse(body, count)
        parsed.append(data)
        files[name] = {"bytes": size, "sha256": h, "layout": formats}
    prior, current = parsed
    old = {key for key in current if key[-1] < 189}
    need(
        old <= prior.keys() and all(prior[key] == current[key] for key in old),
        "prefix cells modified",
    )
    need(
        len(prior) == (189 + 128) * 36 and len(old) == (189 + 125) * 36,
        "retained prefix population",
    )
    for layer in range(14):
        for role in ("K", "V"):
            for pos in range(189, 192):
                name = f"{pos}.{role}cur-{layer}.bin"
                p = cap / "boundary" / name
                need(sha(p) == hashes[name], "F32 tensor identity")
                words = struct.unpack("<512f", p.read_bytes())
                need(all(map(math.isfinite, words)), "nonfinite F32 witness")
                expected_row = struct.pack("<512e", *words)
                need(
                    current[layer, role, pos] == expected_row, "KV association to captured " + name
                )
    return current, dict(
        arm_sha256=expected,
        files=files,
        surviving_prior_component_rows=len(old),
        expired_prior_component_rows=len(prior) - len(old),
        f32_rows_validated=84,
    )


def contrast(ref, actual, width=512):
    need(ref.keys() == actual.keys(), "logical KV inventory changed")
    changed = []
    total = 0
    for (layer, role, pos), a in sorted(ref.items()):
        b = actual[layer, role, pos]
        need(len(a) == len(b) == 2 * width, "paired row length")
        if a == b:
            continue
        x = struct.unpack(f"<{width}H", a)
        y = struct.unpack(f"<{width}H", b)
        which = [i for i in range(width) if x[i] != y[i]]
        need(which, "byte comparison inconsistent")
        changed.append(
            dict(
                layer=layer,
                role=role,
                position=pos,
                changed_words=len(which),
                words=width,
                first_index=which[0],
            )
        )
        total += len(which)

    def first(rows):
        n = min((r["layer"] for r in rows), default=None)
        return [r for r in rows if r["layer"] == n]

    return dict(
        rows=len(ref),
        words=len(ref) * width,
        changed_words=total,
        changed_rows=len(changed),
        first=first(changed),
        first_per_position={
            str(p): first([r for r in changed if r["position"] == p]) for p in range(189, 192)
        },
        changes=changed,
    )


def run(a):
    for file, h in FILES.items():
        need(sha(a.backend / file) == h, "C269 source " + file)
    refs = {}
    receipt = {}
    for mode in ("AR", "OFF", "ON"):
        root = a.archived if mode == "AR" else a.family
        need(sha(root / "receipt.json") == (AR if mode == "AR" else FAMILY), "family hash")
        refs[mode], receipt[mode] = load_arm(
            root, mode, read(root / "receipt.json")["arms"][mode]["receipt_sha256"]
        )
    need(
        len({r["files"]["initial-kv.bin"]["sha256"] for r in receipt.values()}) == 1,
        "different initial snapshots",
    )
    results = {m: contrast(refs["AR"], refs[m]) for m in ("OFF", "ON")}
    need(
        all(c["position"] >= 189 for r in results.values() for c in r["changes"]),
        "changed old cell",
    )
    return dict(
        status="LOCALIZED_SERIALIZED_F16_DIFFERENCES",
        source_commit=PIN,
        study_sha256=sha(Path(__file__).with_name("protocol.md")),
        family_sha256=FAMILY,
        reference_family_sha256=AR,
        inputs=receipt,
        comparisons=results,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("backend", "family", "archived", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        record = run(a)
    except Exception as e:
        record = {"status": "INCONCLUSIVE_KV_LAYOUT_OR_INTEGRITY", "reason": str(e)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    print(record["status"])
    raise SystemExit(int(record["status"].startswith("INCONCLUSIVE")))
