"""Authenticate the two full-model cuts and the original routed GGUF ranges."""

import hashlib
import json
import math
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ATT = HERE.parent / "serial_reference/attention/row_operator"
BASE = run_path(str(ATT / "operands.py"))
R, need, sha, read, save = (BASE[k] for k in ("R", "need", "sha", "read", "save"))
SERIAL = BASE["FAMILY"]
BLOCK = "fb96dbf9d1874808dbfc2170778106e7fec41a09ed36dfabde630e88f843dc58"
METHOD = "547fbea1a9f7d2cca1b43526e00fa1daee56ee4daf7c80644a618f8afc4c7c57"
POSITIONS = range(189, 192)
WIDTH = 2880
ROLES = ("gate", "up", "down")
TAGS = ("A", "B", "U", "D", "S", "F", "B-alt", "F-alt", "mutant")


def floats(data, size):
    need(len(data) == 4 * size, "F32 cardinality")
    values = struct.unpack(f"<{size}f", data)
    need(all(map(math.isfinite, values)), "nonfinite F32")
    return values


def capture(root, run, arm):
    prefix = run["unit"] + "-" + arm.lower()
    raw = root / arm / "raw"
    log = (raw / (prefix + ".stderr")).read_text()
    need(
        "layer  25 assigned to device CUDA0, is_swa = 0" in log
        and "40 of 128 experts cached per layer, 4 I/O threads" in log,
        "native layer and cache",
    )
    cap = raw / (prefix + ".capture") / "boundary"
    geometry = [line.split("\t") for line in (cap / "geometry.tsv").read_text().splitlines()]
    data = {}
    width = 1 if arm == "AR" else 3
    for key, name, op, ne, nb in (
        (
            "activation.f32",
            "attn_post_norm",
            "MUL",
            [WIDTH, width, 1, 1],
            [4, 11520, 11520 * width, 11520 * width],
        ),
        (
            "logical.i32",
            "ffn_moe_topk",
            "VIEW",
            [4, width, 1, 1],
            [4, 512, 512 * width, 512 * width],
        ),
        ("mix.f32", "ffn_moe_weights_softmax", "RESHAPE", [1, 4, width, 1], [4, 4, 16, 16 * width]),
        (
            "ffn.f32",
            "ffn_moe_out",
            "ADD",
            [WIDTH, width, 1, 1],
            [4, 11520, 11520 * width, 11520 * width],
        ),
    ):
        label = name + "-25"
        for pos in POSITIONS if width == 1 else (189,):
            (g,) = [row for row in geometry if row[:3] == [str(pos), str(width), label]]
            need(g[3] == op and list(map(int, g[4:])) == ne + nb, "native geometry " + label)
        data[key] = b"".join((cap / f"{pos}.{label}.bin").read_bytes() for pos in POSITIONS)
    for key in ("activation.f32", "ffn.f32"):
        floats(data[key], 3 * WIDTH)
    ids = struct.unpack("<12i", data["logical.i32"])
    weights = floats(data["mix.f32"], 12)
    for i in range(0, 12, 4):
        row = ids[i : i + 4]
        need(len(set(row)) == 4 and min(row) >= 0 and max(row) < 128, "target top four")
        need(
            min(weights[i : i + 4]) > 0 and abs(sum(weights[i : i + 4]) - 1) < 1e-6,
            "target mixture",
        )
    return data


def references(serial, block):
    a = R["reopen"](serial, SERIAL)
    b = R["reopen"](block, BLOCK)
    need(
        b["parent_sha256"] == SERIAL and b["status"] == "RESTORED_L25_ATTENTION_PARTIAL",
        "target linkage",
    )
    inputs = capture(serial, a, "AR")
    other = capture(block, b, "ON")
    refs = {"AR": inputs.pop("ffn.f32"), "B3": other.pop("ffn.f32")}
    need(inputs == other, "same activations, ranks and mixture")
    return inputs, refs


def components(model, inventory, config, ids, dest):
    need(sha(inventory) == BASE["INVENTORY"], "GGUF inventory")
    entries = [json.loads(line) for line in inventory.read_bytes().splitlines()]
    stamp = config["model_stat"]
    ranges = {}
    with model.open("rb", buffering=0) as f:
        need(BASE["stat_id"](os.fstat(f.fileno())) == stamp, "GGUF generation")
        for role in ROLES:
            for suffix, kind, dims, slab in (
                ("weight", "mxfp4", [WIDTH, WIDTH, 128], 4406400),
                ("bias", "f32", [WIDTH, 128], WIDTH * 4),
            ):
                name = f"blk.25.ffn_{role}_exps.{suffix}"
                (row,) = [r for r in entries if r.get("name") == name]
                need(
                    row["shape"] == dims
                    and row["tensor_type"] == kind
                    and row["n_bytes"] == 128 * slab,
                    name,
                )
                for expert in sorted(set(ids)):
                    offset = row["data_offset"] + expert * slab
                    need(0 <= offset <= stamp["size_bytes"] - slab, "GGUF range")
                    blob = os.pread(f.fileno(), slab, offset)
                    need(len(blob) == slab, "GGUF pread")
                    if suffix == "bias":
                        floats(blob, WIDTH)
                    file = f"{role}.{suffix}.{expert}"
                    record = dict(
                        tensor=name,
                        expert=expert,
                        offset=offset,
                        bytes=slab,
                        sha256=hashlib.sha256(blob).hexdigest(),
                    )
                    ranges[file] = record
                    if dest is not None:
                        with (dest / file).open("xb") as out:
                            out.write(blob)
        need(
            BASE["stat_id"](os.fstat(f.fileno())) == BASE["stat_id"](model.stat()) == stamp,
            "GGUF generation after reads",
        )
    return ranges


def comparisons(data, ref):
    floats(data, 3 * WIDTH)
    floats(ref, 3 * WIDTH)
    results = []
    for i in range(3):
        sl = slice(i * WIDTH * 4, (i + 1) * WIDTH * 4)
        x, y = data[sl], ref[sl]
        vx, vy = floats(x, WIDTH), floats(y, WIDTH)
        idx = [
            k
            for k, (a, b) in enumerate(
                zip(struct.iter_unpack("<I", x), struct.iter_unpack("<I", y), strict=True)
            )
            if a != b
        ]
        results.append(
            dict(
                position=189 + i,
                different=len(idx),
                first=idx[0] if idx else None,
                max_abs=max(abs(a - b) for a, b in zip(vx, vy, strict=True)),
                sha256=hashlib.sha256(x).hexdigest(),
            )
        )
    return results


def grade(outputs, refs, ids):
    need(set(outputs) == set(TAGS), "arm coverage")
    rows = {
        tag: {k: comparisons(data, ref) for k, ref in refs.items()} for tag, data in outputs.items()
    }
    need(
        [r["different"] for r in comparisons(refs["B3"], refs["AR"])] == [33, 29, 109],
        "sealed full-model controls",
    )
    data, mutant = outputs["B"], outputs["mutant"]
    changed = [i for i in range(3 * WIDTH) if data[4 * i : 4 * i + 4] != mutant[4 * i : 4 * i + 4]]
    expected = [j * WIDTH for j in range(3) if ids[0] in ids[4 * j : 4 * j + 4]]
    if outputs["A"] != refs["AR"] or data != refs["B3"]:
        status = "INCONCLUSIVE_NATIVE_FFN_BASELINES"
    elif (
        outputs["B-alt"] != data
        or outputs["F-alt"] != outputs["F"]
        or not changed
        or changed != expected
    ):
        status = "INCONCLUSIVE_FFN_CONTROLS"
    elif any(outputs[t] == refs["AR"] for t in ("U", "D", "S", "F")):
        status = "GO_EXACT_FFN_OPERATOR"
    else:
        status = "NO_GO_ROW_FFN_OPERATOR"
    return dict(
        decision=status,
        rows=rows,
        mutation_coordinates=changed,
        matched_serial=[t for t in ("U", "D", "S", "F") if outputs[t] == refs["AR"]],
    )
