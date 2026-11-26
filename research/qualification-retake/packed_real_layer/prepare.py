"""Prepare the five committed CPU0 records and two sealed historical captures."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
from pathlib import Path

MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
MODEL_SIZE = 63_387_346_208
PLACEMENT = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
META = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
REFS = {
    "C265": "63bd0fe02a02405da3b23ee799f471f66b78a1864cdad88b354bee6cbc546902",
    "C266": "ae0271cda1caca1547d517185a4c74fa16bb10dae393d3032ffb522fd9136dcc",
    "C270": "b073d6708e50df31f6f71a4c5dc1b3102222ab23b62215ad0238ffa439ebf4e3",
    "rows153": "1562f0a38a8cb7663da379f9eb7b016a03f1f2cdc45c766c0c33eead76508e7c",
    "C266_CPU0_stdout": "aa71877afd1ce43f1f56988105af75021d649fe842ae47d39402c3a06b0fe5bf",
}
C265 = "c265-native-probs-alias-repair-20261004"
C266 = "c266-new-shape-native-canonical-reference-20261004"
C270 = "c270-last-use-ordered-fidelity-20261004"
C290 = "c290-integral-lossless-store-20261006/raw/integral-index.json"
INVENTORY = (
    "c283-exact-expert-service-epoch-20261006T194311Z/build/model-tensor-metadata.jsonl"
)
EXPERTS = (45, 49, 57, 60, 98)
ROLES = ("gate", "down", "up")
WIDTH, SLAB, BIAS, WINDOW, STRIDE = 2880, 4_406_400, 11_520, 13_221_888, 13_258_752
SOURCE_BYTES = 67_743_872
SHAPES = {
    "attn_post_norm": [WIDTH, 153, 1, 1],
    "ffn_moe_logits": [128, 153, 1, 1],
    "ffn_moe_logits_biased": [128, 153, 1, 1],
    "ffn_moe_topk": [4, 153, 1, 1],
    "ffn_moe_weights_softmax": [1, 4, 153, 1],
    "ffn_moe_out": [WIDTH, 153, 1, 1],
}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def authenticated(path, digest, length=None):
    info = path.lstat()
    need(
        stat.S_ISREG(info.st_mode)
        and info.st_size <= 16 << 20
        and (length is None or info.st_size == length),
        "invalid file size/type: " + path.name,
    )
    blob = path.read_bytes()
    need(
        len(blob) == info.st_size and sha(blob) == digest,
        "digest mismatch: " + path.name,
    )
    return blob


def write(out, filename, data, report):
    with (out / filename).open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    digest = sha(data)
    need(file_sha(out / filename) == digest, "output readback: " + filename)
    report["file_sha256"][filename] = digest


def check_routing(blob):
    rows = list(struct.iter_unpack("<4i", blob))
    need(
        len(rows) == 153
        and all(len(set(r)) == 4 and 0 <= min(r) <= max(r) < 128 for r in rows),
        "ordered routing shape or ID",
    )
    tile = rows[32:64]
    need(
        sorted(set().union(*tile)) == list(EXPERTS) and len(set(tile)) == 7,
        "selected tile differs",
    )


def captures(repo, results, out, report):
    old = json.loads(authenticated(results / C265 / "raw-manifest.json", REFS["C265"]))[
        "files"
    ]
    new = json.loads(authenticated(results / C270 / "raw-manifest.json", REFS["C270"]))[
        "files"
    ]
    c266 = json.loads(
        authenticated(results / C266 / "raw-manifest.json", REFS["C266"])
    )["files"]
    gold = c266["raw/c266-layer0.stdout"]
    need(gold["sha256"] == REFS["C266_CPU0_stdout"], "independent reference identity")
    authenticated(
        results / C266 / "raw/c266-layer0.stdout", gold["sha256"], gold["bytes"]
    )
    authenticated(
        repo / "research/qualification-retake/rows153/receipts/r2.json", REFS["rows153"]
    )
    items = {r["path"]: r for r in new}
    need(len(items) == len(new), "duplicate historical capture")
    histories = []
    for n, run in ((C265, "c265-tile"), (C270, "c270-ordered")):
        base = Path("raw") / (run + ".capture")
        if n == C265:
            lookup = {
                k.removeprefix(str(base) + "/"): (r["bytes"], r["sha256"])
                for k, r in old.items()
                if k.startswith(str(base) + "/")
            }
        else:
            prefix = "results/" + n + "/" + str(base) + "/"
            lookup = {
                k.removeprefix(prefix): (r["size"], r["sha256"])
                for k, r in items.items()
                if k.startswith(prefix)
            }
        root = results / n / base
        size, digest = lookup["result.json"]
        stages = json.loads(authenticated(root / "result.json", digest, size))["stages"]
        contents = {}
        for stage, shape in SHAPES.items():
            filename = stage + "-0.bin"
            matching = [s for s in stages if s.get("file") == filename]
            need(len(matching) == 1, "missing/duplicate historical stage")
            row = matching[0]
            size, digest = lookup[filename]
            need(
                row["ne"] == shape
                and row["bytes"]
                == size
                == 4 * shape[0] * shape[1] * shape[2] * shape[3]
                and row["dtype"] == ("i32" if stage == "ffn_moe_topk" else "f32")
                and row["layer"] == 0
                and row["stage"] == stage,
                "historical shape or type",
            )
            contents[filename] = authenticated(root / filename, digest, size)
        histories.append(contents)
    need(histories[0] == histories[1], "C265 and C270 differ")
    check_routing(histories[0]["ffn_moe_topk-0.bin"])
    for name, blob in histories[0].items():
        write(out, name, blob, report)
    report["capture_refs"] = REFS


def layout(index, metadata):
    need(
        index["model_sha256_previous_verified"] == MODEL
        and index["metadata_sha256"] == META
        and (index["weight_window"], index["stride"], index["alignment"])
        == (WINDOW, STRIDE, 4096)
        and len(index["experts"]) == 4608,
        "C290 geometry or identity",
    )
    header, *entries = metadata
    tensors = {t["name"]: t for t in entries}
    need(
        header["schema"] == "tesy.gguf_native_inventory_header.v1"
        and header["gguf_version"] == 3
        and len(tensors) == len(entries) == header["tensor_count"] == 687,
        "GGUF inventory",
    )

    def tensor(name, shape, dtype, length):
        t = tensors["blk.0.ffn_" + name]
        offset = t["data_offset"]
        need(
            t["shape"] == shape
            and t["tensor_type"] == dtype
            and t["n_bytes"] == length
            and offset == header["data_offset"] + t["relative_data_offset"]
            and 0 <= offset <= MODEL_SIZE - length
            and offset % header["alignment"] == 0,
            "tensor metadata: " + name,
        )
        return offset

    router = {
        "weight": (
            tensor("gate_inp.weight", [WIDTH, 128], "f32", WIDTH * 128 * 4),
            WIDTH * 128 * 4,
        ),
        "bias": (tensor("gate_inp.bias", [128], "f32", 128 * 4), 128 * 4),
    }
    names = [role + "_exps." + kind for kind in ("weight", "bias") for role in ROLES]
    sizes = [SLAB] * 3 + [BIAS] * 3
    types = ["mxfp4"] * 3 + ["f32"] * 3
    offsets = [0, SLAB, 2 * SLAB, WINDOW, WINDOW + BIAS, WINDOW + 2 * BIAS]
    bases = [
        tensor(
            n, [WIDTH, WIDTH, 128] if i < 3 else [WIDTH, 128], types[i], sizes[i] * 128
        )
        for i, n in enumerate(names)
    ]
    selected = {}
    for expert in EXPERTS:
        row = index["experts"][expert]
        need(
            (row["layer"], row["expert"], row["tier"], row["pack_offset"])
            == (0, expert, "CPU", expert * STRIDE)
            and len(row["components"]) == 6,
            "expert record index",
        )
        for i, c in enumerate(row["components"]):
            need(
                c["name"] == "blk.0.ffn_" + names[i]
                and c["size_bytes"] == sizes[i]
                and c["type"] == types[i]
                and c["packed_relative_offset"] == offsets[i]
                and c["source_offset"] == bases[i] + expert * sizes[i]
                and re.fullmatch("[a-f0-9]{64}", c["sha256"]),
                "expert component mapping",
            )
        selected[expert] = row["components"]
    return bases[:3], router, selected


def identity(st):
    return {
        k: getattr(st, "st_" + k)
        for k in ("dev", "ino", "size", "mtime_ns", "ctime_ns")
    }


def mount(path):
    raw = subprocess.check_output(
        ["findmnt", "-J", "-T", str(path), "-o", "SOURCE,FSTYPE"], timeout=5
    )
    rows = json.loads(raw)["filesystems"]
    need(len(rows) == 1 and rows[0]["fstype"] == "btrfs", "expected Btrfs")
    device = rows[0]["source"].split("[")[0]
    need(re.fullmatch(r"/dev/nvme\d+n\d+(p\d+)?", device), "expected internal NVMe")
    return {"filesystem": "btrfs", "device": Path(device).name}


def fetch(fd, offset, length, digest, report):
    need(
        0 <= offset <= MODEL_SIZE - length
        and length > 0
        and report["gguf_read_bytes"] + length <= SOURCE_BYTES,
        "source range or budget",
    )
    report["gguf_read_bytes"] += length
    report["gguf_reads"] += 1
    data = os.pread(fd, length, offset)
    report["gguf_returned_bytes"] += len(data)
    need(
        len(data) == length and (digest is None or sha(data) == digest),
        "short read or component SHA",
    )
    return data


def verify_record(data, components):
    end = 0
    for c in components:
        at = c["packed_relative_offset"]
        stop = at + c["size_bytes"]
        need(
            0 <= end <= at < stop <= len(data) and not any(data[end:at]),
            "packed offset or padding",
        )
        need(
            sha(memoryview(data)[at:stop]) == c["sha256"], "persisted component digest"
        )
        end = stop
    need(not any(data[end:]), "nonzero end padding")


def materialize(fd, out, router, selected, report):
    biases = {name: bytearray(WIDTH * 128 * 4) for name in ROLES}
    stream_hash = hashlib.sha256()
    with (out / "pack.bin").open("xb") as f:
        for expert in EXPERTS:
            record = bytearray(STRIDE)
            for c in selected[expert]:
                blob = fetch(
                    fd, c["source_offset"], c["size_bytes"], c["sha256"], report
                )
                pos = c["packed_relative_offset"]
                record[pos : pos + len(blob)] = blob
                if c["name"].endswith(".bias"):
                    role = c["name"].split("ffn_")[1].split("_")[0]
                    biases[role][expert * BIAS : (expert + 1) * BIAS] = blob
            stream_hash.update(record)
            f.write(record)
        f.flush()
        os.fsync(f.fileno())
    pack = out / "pack.bin"
    reread = hashlib.sha256()
    with pack.open("rb") as source:
        for expert in EXPERTS:
            blob = source.read(STRIDE)
            need(len(blob) == STRIDE, "incomplete output record")
            verify_record(blob, selected[expert])
            reread.update(blob)
        need(
            not source.read(1) and reread.digest() == stream_hash.digest(),
            "pack readback",
        )
    report["pack_readback_bytes"] = len(EXPERTS) * STRIDE
    report["file_sha256"]["pack.bin"] = stream_hash.hexdigest()
    report["pack_identity"] = identity(pack.stat())
    for role, data in biases.items():
        write(out, role + ".bias", data, report)
    for role, (offset, length) in router.items():
        write(out, "router." + role, fetch(fd, offset, length, None, report), report)
    report.update(
        components_verified=30,
        weight_window_padding_bytes_per_record=WINDOW - 3 * SLAB,
        record_tail_padding_bytes_per_record=STRIDE - WINDOW - 3 * BIAS,
        pack_size_bytes=5 * STRIDE,
        router_source_offsets={k: o for k, (o, _) in router.items()},
    )
    need(
        report["gguf_read_bytes"] == report["gguf_returned_bytes"] == SOURCE_BYTES
        and report["gguf_reads"] == 32,
        "source conservation",
    )


def prepare(args, report):
    repo, results, out = args.repo, args.lab / "results", args.new_output_dir
    place = json.loads(authenticated(args.placement, PLACEMENT))
    need(
        place["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and place["source_sha256"] == MODEL
        and place["destination_direct_reread"]["sha256"] == MODEL
        and place["source_size"]
        == place["destination_direct_reread"]["size_bytes"]
        == MODEL_SIZE
        and place["destination_transport"] == "nvme",
        "placement receipt",
    )
    model = Path(place["working_copy"])
    need(
        model.resolve(strict=True) == model
        and model.samefile(args.model)
        and model.samefile(place["launcher_path"]),
        "placed model path identity",
    )
    report["model_mount"], report["pack_mount"] = mount(model), mount(out)
    need(
        report["model_mount"] == report["pack_mount"]
        and shutil.disk_usage(out).free > 128 << 20,
        "pack device/capacity",
    )
    captures(repo, results, out, report)
    idx = json.loads(authenticated(results / C290, INDEX))
    meta = [
        json.loads(s) for s in authenticated(results / INVENTORY, META).splitlines()
    ]
    bases, router, selected = layout(idx, meta)
    report.update(
        weight_bases=bases,
        index_sha256=INDEX,
        metadata_sha256=META,
        model_sha256=MODEL,
        placement_sha256=PLACEMENT,
        ordered_experts=EXPERTS,
        components={str(k): v for k, v in selected.items()},
    )
    with os.fdopen(
        os.open(model, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb", buffering=0
    ) as src:
        fd = src.fileno()
        st = os.fstat(fd)
        opening = identity(st)
        need(
            stat.S_ISREG(st.st_mode)
            and st.st_size == MODEL_SIZE
            and st.st_ctime_ns <= args.placement.stat().st_mtime_ns
            and opening == identity(model.stat()) == identity(args.model.stat()),
            "placed file descriptor or age",
        )
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        materialize(fd, out, router, selected, report)
        need(
            opening
            == identity(os.fstat(fd))
            == identity(model.stat())
            == identity(args.model.stat()),
            "model changed while preparing",
        )
        report["model_fd_identity"] = opening
    report["prepared_files_bytes"] = sum(
        (out / n).stat().st_size for n in report["file_sha256"]
    )
    need(
        len(report["file_sha256"]) == 12
        and report["prepared_files_bytes"] <= 128 << 20,
        "prepared file cap",
    )
    report["status"] = "PASS_PREPARED_REAL_TILE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "lab", "model", "placement", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir(exist_ok=False)
    report = {
        "schema": "tesy-packed-cpu0-c290-tile-inputs-v1",
        "status": "FAIL_PRESERVED",
        "gguf_read_bytes": 0,
        "gguf_returned_bytes": 0,
        "gguf_reads": 0,
        "file_sha256": {},
        "program_sha256": file_sha(Path(__file__)),
    }
    try:
        prepare(args, report)
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        report["reason"] = f"{type(error).__name__}: {error}"
    tmp = out / "prepare.pending"
    with tmp.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.link(tmp, out / "prepare.json")
    tmp.unlink()
    print(report["status"])
    return int(report["status"] != "PASS_PREPARED_REAL_TILE")


if __name__ == "__main__":
    raise SystemExit(main())
