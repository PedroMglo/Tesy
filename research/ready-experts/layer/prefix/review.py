"""Regrade the public clocks and optionally verify both journals and private originals."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence-20261128-r01"
grade = run_path(HERE / "grade.py")
need = grade["need"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def review(raw=None, traces=None):
    d = read(EVIDENCE / "decision.json")
    p = d["provenance"]
    for name, wanted in d["artifacts_sha256"].items():
        need(sha((EVIDENCE / name).read_bytes()) == wanted, name)
    for name, wanted in p["build"]["source_sha256"].items():
        need(sha((HERE / name).read_bytes()) == wanted, name)
    checks = {
        "physical.py": p["consumer"]["source_sha256"],
        "grade.py": p["consumer"]["grader_sha256"],
        "pair.py": p["pair"]["program_sha256"],
        "pair-protocol.md": p["pair"]["protocol_sha256"],
    }
    for stem in ("reach", "batch"):
        r = read(EVIDENCE / (stem + ".json"))
        checks[stem + ".py"] = r["source_sha256"]
        checks[stem + "-protocol.md"] = r["protocol_sha256"]
        for label, a in r["arms"].items():
            need(a["journal_sha256"] == d["pair"]["sources"][label], "journal identity")
        if traces is not None:
            need(run_path(HERE / (stem + ".py"))["run"](traces) == r, "journal replay " + stem)
    for name, wanted in checks.items():
        need(sha((HERE / name).read_bytes()) == wanted, name)
    rows = gzip.decompress((EVIDENCE / "consumer-arms.json.gz").read_bytes())
    need(
        sha(rows) == p["consumer"]["stdout_sha256"]
        and grade["grade"](json.loads(rows)) == d["consumer"],
        "full FFN arm clocks",
    )
    pairs = gzip.decompress((EVIDENCE / "pair-arms.jsonl.gz").read_bytes())
    arms = [json.loads(line) for line in pairs.splitlines()]
    io = d["pair"]
    need(
        sha(pairs) == p["pair_arms_sha256"]
        and run_path(HERE / "pair.py")["grade"](arms) == io["cases"]
        and sum(a["requested_bytes"] for a in arms) == io["logical_bytes"],
        "pair transport",
    )
    plan = io["selection"]
    need(
        all(
            abs(records[0]["offset"] - records[1]["offset"]) == 13221888 + 36864
            for records in (case["records"] for case in plan.values())
        ),
        "actual adjacent extents",
    )
    if raw is not None:
        receipt = read(EVIDENCE / "archive.json")
        verify = HERE.parents[2] / "qualification-retake/private_archive/verify.py"
        run_path(verify)["verify"](raw, receipt)
        part = raw / receipt["part"]
        for name, digest in p["physical_raw_receipts"].items():
            need(sha((part / name / "receipt.json").read_bytes()) == digest, name)
        need(
            (part / "tesy-prefix-consumer-20261128-r01/stdout").read_bytes() == rows
            and (part / "tesy-coalesced-pairs-20261128-r01/arms.jsonl").read_bytes() == pairs,
            "raw clocks",
        )
        need(
            sha((part / "reach-r01/failure.json").read_bytes()) == p["reach_r01_failure"]["sha256"],
            "original failure",
        )
        for name, folder in (("reach.json", "reach-r02"), ("batch.json", "batch-r01")):
            need(
                (EVIDENCE / name).read_bytes() == (part / folder / "receipt.json").read_bytes(),
                name,
            )
    fifo_path = HERE / "evidence-fifo-20261128-r01/receipt.json"
    fifo = read(fifo_path)
    seal = "c4da12c30db61c7213007a03bbf677f6eea72692687b23b11df1ccec021d5644"
    need(
        sha(fifo_path.read_bytes()) == seal
        and fifo["parent_sha256"] == sha((EVIDENCE / "decision.json").read_bytes())
        and fifo["program_sha256"] == sha((HERE / "fifo.py").read_bytes())
        and fifo["protocol_sha256"] == sha((HERE / "fifo-protocol.md").read_bytes()),
        "FIFO diagnostic identity",
    )
    for label, arm in fifo["arms"].items():
        before = arm["pairs"]["prefill"]
        after = arm["pairs"]["decode"]
        need(
            arm["journal_sha256"] == io["sources"][label]
            and arm["counts"]["claim"] == arm["counts"]["publish"] == 2354
            and before["queue_depth"] == 7
            and before["other_index"] == 3
            and [k[3] for k in before["intervening"]] == [3, 10]
            and after["queue_depth"] == 2
            and after["head_adjacent"]
            and after["other_index"] == 1,
            "measured pair admission",
        )
    if traces is not None:
        need(run_path(HERE / "fifo.py")["run"](traces) == fifo, "FIFO replay")
    return {k: r["decision"] for k, r in d["consumer"]["families"].items()} | {
        f"pair_{k}": r["decision"] for k, r in io["cases"].items()
    }


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--raw-archive", type=Path)
    a.add_argument("--trace-archive", type=Path)
    args = a.parse_args()
    print(json.dumps(review(args.raw_archive, args.trace_archive), sort_keys=True))
