"""Independently check every archived F32 against the public decision, including the fault arms."""

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GRADE = run_path(HERE / "grade.py")
need = GRADE["need"]
SPAN = GRADE["SPAN"]


def verify(evidence, archive):
    audit = run_path(HERE.parents[5] / "qualification-retake/private_archive/verify.py")
    archive_receipt = json.loads((evidence / "archive.json").read_bytes())
    count, size = audit["verify"](archive, archive_receipt)
    rel = archive / archive_receipt["part"]
    raw = rel / "tesy-renewal-run-20261128-r01"
    samples = json.loads(gzip.decompress((evidence / "samples.json.gz").read_bytes()))
    need(
        (raw / "samples.json.gz").read_bytes() == (evidence / "samples.json.gz").read_bytes(),
        "private samples differ",
    )
    decision = json.loads((evidence / "decision.json").read_bytes())
    need(GRADE["grade"](samples) == decision, "published price and exact arms")
    ref = None
    for role in ("DISK", "COPY", "ID", "WRONG", "EIO"):
        data = (raw / "raw" / ("exact-" + role + ".f32")).read_bytes()
        n = 3 if role == "EIO" else 12
        need(len(data) == n * SPAN * 4, "F32 count")
        need(
            all(word & 0x7F800000 != 0x7F800000 for (word,) in struct.iter_unpack("<I", data)),
            "nonfinite archived output",
        )
        parts = [data[4 * k * SPAN : 4 * (k + 1) * SPAN] for k in range(n)]
        if role == "DISK":
            ref = parts
        if role == "EIO":
            need(parts == ref[:3], "EIO reference before fault")
            continue
        actual = samples["exact"][role]["rows"]
        recorded = [h for row in actual for h in row["hashes"]["sha256"]]
        first = [h for row in actual for h in row["hashes"]["first_rank"]]
        need(
            recorded == [hashlib.sha256(p).hexdigest() for p in parts]
            and first == [hashlib.sha256(p[:SPAN]).hexdigest() for p in parts],
            "rank digests",
        )
        if role != "DISK":
            diff = [
                sum(
                    a != b
                    for a, b in zip(
                        struct.iter_unpack("<I", p), struct.iter_unpack("<I", q), strict=True
                    )
                )
                for p, q in zip(parts, ref, strict=True)
            ]
            need(diff == samples["differences"][role], "archived numerical difference")
    return count, size


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("evidence", type=Path)
    p.add_argument("archive", type=Path)
    a = p.parse_args()
    print("PASS_ARCHIVED_F32", *verify(a.evidence, a.archive))
