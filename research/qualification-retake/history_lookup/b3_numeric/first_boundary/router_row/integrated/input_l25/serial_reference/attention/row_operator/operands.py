"""Reconstruct and seal the layer-25 operands from the two synchronized model executions."""

import hashlib
import json
import math
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE.parent / "pair.py"))
R, S, need, read, sha, save = (P[k] for k in ("R", "S", "need", "read", "sha", "save"))
KV = run_path(str(S["QUAL"] / "history_lookup/b3_numeric/kv_difference/screen.py"))
FAMILY = "72819fc1e0f5c31b688c81d554e22693b04ba29feb26d8303253bdc1ec9af777"
EVIDENCE = "b8678e61154755cb2f95d2de74bfa34d1260b39d50cfa52fcd9dff66cd6bde97"
METHOD = "ef12c164140e4ee4b7d21d314282c928d553088ec1e1a8023b723e7053c0a535"
INVENTORY = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
POSITIONS = range(189, 192)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stat_id(st):
    return dict(
        dev=st.st_dev,
        inode=st.st_ino,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )


def sinks(model, inventory, reference):
    need(sha(inventory) == INVENTORY, "C7 inventory")
    entries = [json.loads(line) for line in inventory.read_bytes().splitlines()]
    (row,) = [r for r in entries if r.get("name") == "blk.25.attn_sinks.weight"]
    need(
        row["data_offset"] == 44425683232
        and row["shape"] == [64]
        and row["n_bytes"] == 256
        and row["tensor_type"] == "f32",
        "sink metadata",
    )
    with model.open("rb", buffering=0) as f:
        need(stat_id(os.fstat(f.fileno())) == reference, "GGUF identity")
        data = os.pread(f.fileno(), 256, row["data_offset"])
        need(stat_id(os.fstat(f.fileno())) == stat_id(model.stat()) == reference, "GGUF changed")
    need(len(data) == 256 and all(map(math.isfinite, struct.unpack("<64f", data))), "finite sinks")
    return data


def from_arm(family, run, mode):
    unit = run["unit"] + "-" + mode.lower()
    raw = family / mode / "raw"
    cap = raw / (unit + ".capture")
    log = (raw / (unit + ".stderr")).read_bytes()
    need(
        b"layer  25 assigned to device CUDA0, is_swa = 0" in log
        and b"compute capability 8.9" in log,
        "physical attention placement",
    )
    banks = KV["layers_from_log"](log)
    matrices = {}
    for name, count in (("initial", 189), ("post3", 192)):
        blob = (cap / (name + "-kv.bin")).read_bytes()
        rows, _ = KV["parse"](blob, count, banks)
        for role in ("K", "V"):
            offsets = [rows["base", role, 25, pos] for pos in range(count)]
            need(
                offsets == list(range(offsets[0], offsets[0] + 1024 * count, 1024)), "F16 row order"
            )
            matrices[name, role] = blob[offsets[0] : offsets[-1] + 1024]
    data = {}
    for role in ("K", "V"):
        old, new = (matrices[k, role] for k in ("initial", "post3"))
        need(new.startswith(old) and len(new) == 192 * 1024, "unchanged populated prefix")
        for pos in POSITIONS:
            values = struct.unpack(
                "<512f", (cap / "boundary" / f"{pos}.{role}cur-25.bin").read_bytes()
            )
            need(
                struct.pack("<512e", *values) == new[pos * 1024 : (pos + 1) * 1024],
                "new KV vs target F32",
            )
        data[role.lower() + ".f16"] = new
    data["q.f32"] = b"".join(
        (cap / "boundary" / f"{p}.Qcur-25.bin").read_bytes() for p in POSITIONS
    )
    masks = []
    for pos in POSITIONS:
        file = cap / f"mask-25-{pos}.f16"
        need(P["mask"](file) == (0,) * (pos + 1) + (0xFC00,) * (255 - pos), "causal physical cells")
        masks.append(file.read_bytes())
    data["mask.f16"] = b"".join(masks)
    output = b"".join((cap / "boundary" / f"{p}.{P['NAME']}.bin").read_bytes() for p in POSITIONS)
    need(len(output) == len(data["q.f32"]) == 3 * 4096 * 4, "three real rows")
    return data, output


def reconstruct(family, model, inventory):
    run = R["reopen"](family, FAMILY)
    evidence = HERE.parent / "result.json"
    need(
        sha(evidence) == EVIDENCE
        and read(evidence)["family_sha256"] == FAMILY
        and sha(HERE / "protocol.md") == METHOD,
        "numerical/protocol authority",
    )
    a, ar = from_arm(family, run, "AR")
    b, block = from_arm(family, run, "B3")
    need(a == b, "AR/B3 logical attention operands")
    cfg = read(family / "AR/attention-resource.json")
    need(cfg["pinned"]["model_sha256"] == read(evidence)["model_sha256"], "model authority")
    a["sinks.f32"] = sinks(model, inventory, cfg["model_stat"])
    return a, {"AR": ar, "B3": block}, cfg


def grade(outs, refs):
    result = {}
    for tag, reference in (
        ("A", "AR"),
        ("B", "B3"),
        ("S", "AR"),
        ("B-alt", "B3"),
        ("S-alt", "AR"),
        ("mutant", "B3"),
    ):
        data = outs[tag]
        need(
            len(data) == 3 * 16384 and all(map(math.isfinite, struct.unpack("<12288f", data))),
            "nonfinite or truncated " + tag,
        )
        rows = []
        for i, pos in enumerate(POSITIONS):
            row = data[i * 16384 : (i + 1) * 16384]
            gold = refs[reference][i * 16384 : (i + 1) * 16384]
            ndiff, first = P["G"]["base"].word_diff(gold, row)
            words = struct.unpack("<4096f", row)
            rows.append(
                dict(
                    position=pos,
                    different=ndiff,
                    first=first,
                    sha256=digest(row),
                    reference_sha256=digest(gold),
                    zeros=words.count(0.0),
                )
            )
        result[tag] = rows

    def good(tag):
        return all(r["different"] == 0 for r in result[tag])

    if not (good("A") and good("B")):
        decision = "INCONCLUSIVE_NATIVE_BASELINES"
    elif not (
        outs["B"] == outs["B-alt"]
        and outs["S"] == outs["S-alt"]
        and all(r["zeros"] == 4096 and r["different"] > 0 for r in result["mutant"])
    ):
        decision = "INCONCLUSIVE_FAULT_OR_PADDING"
    elif good("S"):
        decision = "GO_EXACT_ROW_ATTENTION_OPERATOR"
    else:
        decision = "NO_GO_ROW_ATTENTION_OPERATOR"
    return dict(decision=decision, rows=result)
