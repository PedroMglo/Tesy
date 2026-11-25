"""Prepare the eight authenticated native MXFP4 slabs and one C265/C270 activation."""

import argparse
import hashlib
import json
import math
import os
import stat
import struct
from pathlib import Path

INDEX = "f8961dcdaa58aa7774e63150b76d69add0dd080181493838528c8f36de543a57"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
MODEL_BYTES = 63_387_346_208
ACTIVATION = "7904f706fc9bcad58c587e6cc0f93eaea1b975265928e1ff7d8b1907652889dd"
ROUTING = "14ada9ecbfe77401ff5d40955e9b491c6ebc82f34787737c2e4c8910ffa6cd96"
C265 = "c265-native-probs-alias-repair-20261004/raw/c265-tile.capture"
C270 = "c270-last-use-ordered-fidelity-20261004/raw/c270-ordered.capture"
CAPTURES = {
    C265: "857b693e07432b873844cc5fec35e068d81d1bc08a7d75e804f2e1adc9647e84",
    C270: "dd44c31a81421566292c4256518f522e04f3995741daed14f7fc2af4f4f2b6ff",
}
EXPERTS = (28, 73, 46, 56)
WIDTH = 2880
SLAB = 4_406_400


def verify(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    verify(sha(data) == expected, f"{path.name} digest mismatch")
    return data


def activation(results):
    first = None
    for relative, digest in CAPTURES.items():
        root = results / relative
        info = json.loads(checked(root / "result.json", digest))
        blobs = []
        for name, typ, width, h in [
            ("attn_post_norm", "f32", WIDTH, ACTIVATION),
            ("ffn_moe_topk", "i32", 4, ROUTING),
        ]:
            filename = name + "-0.bin"
            rows = [r for r in info["stages"] if r.get("file") == filename]
            verify(len(rows) == 1, "capture row multiplicity")
            r = rows[0]
            verify(
                r["layer"] == 0
                and r["stage"] == name
                and r["dtype"] == typ
                and r["ne"] == [width, 153, 1, 1]
                and r["bytes"] == width * 153 * 4,
                "capture shape",
            )
            payload = checked(root / filename, h)
            verify(len(payload) == r["bytes"], "capture size")
            blobs.append(payload)
        if first is None:
            first = blobs
        else:
            verify(first == blobs, "C265 and C270 disagree")
    row = first[0][: WIDTH * 4]
    verify(struct.unpack_from("<4i", first[1]) == EXPERTS, "first token rank order")
    verify(all(math.isfinite(v) for (v,) in struct.iter_unpack("<f", row)), "nonfinite input")
    return row


def identity(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def prepare(lab, model, output, report):
    results = lab / "results"
    idx = results / "c290-integral-lossless-store-20261006/raw/integral-index.json"
    index = json.loads(checked(idx, INDEX))
    verify(index["model_sha256_previous_verified"] == MODEL, "GGUF identity in C290")
    entries = [x for x in index["experts"] if x["layer"] == 0 and x["expert"] in EXPERTS]
    by_expert = {x["expert"]: x for x in entries}
    verify(len(entries) == len(by_expert) == 4, "C290 routing selection")
    row = activation(results)
    report.update(
        original_gguf_sha256_previously_verified=MODEL,
        c290_index_sha256=INDEX,
        c265_c270_full_activation_sha256=ACTIVATION,
        c265_c270_full_topk_sha256=ROUTING,
        activation_sha256=sha(row),
        ordered_experts=list(EXPERTS),
        width=WIDTH,
        rows_per_slab=WIDTH,
        slab_bytes=SLAB,
        slabs=[],
    )
    content = hashlib.sha256()
    with model.open("rb", buffering=0) as source, (output / "weights.bin").open("xb") as dst:
        fd = source.fileno()
        opening = os.fstat(fd)
        verify(stat.S_ISREG(opening.st_mode) and opening.st_size == MODEL_BYTES, "GGUF size/type")
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for expert in EXPERTS:
            entry = by_expert[expert]
            verify(entry["tier"] == "CPU", "wrong source tier")
            for which in ("gate", "up"):
                name = f"blk.0.ffn_{which}_exps.weight"
                found = [c for c in entry["components"] if c["name"] == name]
                verify(len(found) == 1, "missing/duplicate component")
                c = found[0]
                offset = c["source_offset"]
                verify(
                    c["type"] == "mxfp4"
                    and c["size_bytes"] == SLAB
                    and 0 <= offset <= MODEL_BYTES - SLAB,
                    "invalid C290 weight slice",
                )
                data = os.pread(fd, SLAB, offset)
                verify(
                    len(data) == SLAB and sha(data) == c["sha256"], "original weight slice mismatch"
                )
                report["slabs"].append(
                    dict(
                        expert=expert,
                        matrix=which,
                        gguf_offset=offset,
                        output_offset=dst.tell(),
                        sha256=c["sha256"],
                    )
                )
                dst.write(data)
                content.update(data)
        verify(
            identity(os.fstat(fd)) == identity(opening) == identity(model.stat()), "GGUF FD changed"
        )
    (output / "activation.f32").write_bytes(row)
    with (output / "weights.bin").open("rb") as final:
        verify(hashlib.file_digest(final, "sha256").digest() == content.digest(), "output readback")
    verify((output / "activation.f32").read_bytes() == row, "activation readback")
    report.update(
        status="PASS_AUTHENTICATED_OPERATOR_INPUTS",
        weight_bytes=8 * SLAB,
        weights_sha256=content.hexdigest(),
        activation_bytes=len(row),
        gguf_logical_bytes_read=8 * SLAB,
        source_fd_stable=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("lab", "model", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    root = args.new_output_dir
    os.umask(0o077)
    root.mkdir(exist_ok=False)
    report = {"status": "FAIL_PRESERVED", "schema": "c265-c270-c290-mxfp4-inputs-v1"}
    try:
        prepare(args.lab, args.model, root, report)
    except Exception as error:
        report["reason"] = (
            (type(error).__name__ + ": " + str(error))
            .replace(str(root), "<output>")
            .replace(str(args.lab), "<lab>")
            .replace(str(args.model), "<model>")
        )
    partial = root / ".inputs.pending"
    partial.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    partial.rename(root / "inputs.json")
    print(report["status"])
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
