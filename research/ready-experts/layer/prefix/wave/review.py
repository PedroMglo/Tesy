"""Reproduce the public paired signs and request bounds without a GPU, weights or private data."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
E = HERE / "evidence-20261128-r01"
G = run_path(HERE / "grade.py")
K = run_path(HERE / "bank.py")
P, L, SRC, need = (K[k] for k in ("P", "L", "SRC", "need"))


def get(path):
    return json.loads(path.read_bytes())


def unpack(file):
    return json.loads(gzip.decompress((E / file).read_bytes()))


def canonical(obj):
    return json.loads(json.dumps(obj))


def review(raw=None, traces=None, derived=None):
    prov = get(E / "provenance.json")
    for name, h in prov["artifacts_sha256"].items():
        need(SRC["digest"](E / name) == h, name)
    physical = get(E / "physical.json")
    for name, h in physical["programs"].items():
        need(SRC["digest"](HERE / name) == h, name)
    need(
        SRC["digest"](HERE / "protocol.md") == physical["protocol_sha256"]
        and physical["commit"] == prov["commits"]["physical"]
        and physical["tree"] == prov["trees"]["physical"],
        "physical freeze",
    )
    stream = gzip.decompress((E / "arms.jsonl.gz").read_bytes())
    rows = [json.loads(line) for line in stream.splitlines()]
    measured = canonical(G["grade"](rows, physical["selection"]))
    need(
        hashlib.sha256(stream).hexdigest() == physical["arms_sha256"]
        and measured == physical["result"],
        "physical arms",
    )
    need(
        physical["mutant_rejected"] and physical["model_forwards"] == physical["gpu_compute"] == 0,
        "scope",
    )
    plan = get(E / "plan.json")
    # The public copy puts each layer on one line. Recover the sealed training serialization.
    sealed_plan = (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()
    need(hashlib.sha256(sealed_plan).hexdigest() == P["PLAN"], "sealed T1 bytes")
    layout = SRC["pinned"](E / "layout.json", P["SCORING"])
    pipe = SRC["pinned"](E / "pipeline.json", K["PIPE"])
    bank = get(E / "bank.json")
    for name, rec, field in (
        ("layout", plan, "source_sha256"),
        ("pipeline", pipe, "program_sha256"),
        ("bank", bank, "program_sha256"),
    ):
        need(
            SRC["digest"](HERE / (name + ".py")) == rec[field]
            and SRC["digest"](HERE / (name + "-protocol.md")) == rec["protocol_sha256"],
            name + " freeze",
        )
    regs, service = unpack("regions.json.gz"), unpack("service.json.gz")
    need(
        layout["regions_sha256"] == SRC["digest"](E / "regions.json.gz")
        and bank["service_sha256"] == SRC["digest"](E / "service.json.gz")
        and layout["plan_sha256"] == pipe["plan_sha256"] == bank["plan_sha256"] == P["PLAN"]
        and pipe["layout_receipt_sha256"] == bank["layout_sha256"] == P["SCORING"]
        and bank["pipe_sha256"] == K["PIPE"],
        "composition lineage",
    )
    for tag, base in layout["arms"].items():
        need(
            base["journal_sha256"] == physical["journals"][tag]["journal_sha256"],
            "journal identity",
        )
        framed = base | dict(regions=regs[tag])
        m = pipe["arms"][tag]["markers"]
        for name, path in (("numeric", [list(range(128))] * 36), ("trained", plan["order"])):
            need(L["score"](framed, path) == base[name], "layout reach " + tag)
            need(
                P["price"](framed, m, path) == pipe["arms"][tag][name],
                "pipeline with layout " + tag,
            )
        need(
            P["price"](framed, m, []) == pipe["arms"][tag]["pipeline"], "unmodified layout control"
        )
    paid = K["evaluate"](service["journals"], layout, pipe, plan, service["selected"])
    need(all(bank[k] == v for k, v in paid.items()), "four-worker service and causal RAM")
    if raw:
        archive = get(E / "archive.json")
        run_path(HERE.parents[3] / "qualification-retake/private_archive/verify.py")["verify"](
            raw, archive
        )
        part = raw / archive["part"]
        physical_dir = part / "tesy-wave-coalescing-20261128-r01"
        need(
            (physical_dir / "arms.jsonl").read_bytes() == stream
            and SRC["digest"](physical_dir / "samples.jsonl") == physical["samples_sha256"]
            and SRC["digest"](part / "tesy-wave-coalescing-c55-20261128-r01/receipt.json")
            == physical["c55_sha256"],
            "original clocks, telemetry and C55",
        )
        for src, dst in (
            ("tesy-wave-coalescing-20261128-r01/receipt.json", "physical.json"),
            ("score-r01/receipt.json", "layout.json"),
            ("pipeline-r01/receipt.json", "pipeline.json"),
            ("bank-r01/receipt.json", "bank.json"),
            ("score-r01/regions.json.gz", "regions.json.gz"),
            ("bank-r01/service.json.gz", "service.json.gz"),
        ):
            need((part / src).read_bytes() == (E / dst).read_bytes(), src)
        need((part / "train-r01/receipt.json").read_bytes() == sealed_plan, "original layout")
    if traces:
        name = SRC["SOURCES"]["P106"][0]
        need(canonical(L["train"](traces / "part-106" / name / "ON")) == plan, "sealed T1 layout")
        with TemporaryDirectory() as tmp:
            restored = Path(tmp) / "plan.json"
            restored.write_bytes(sealed_plan)
            evaluation, regions = L["evaluate"](traces, restored, P["PLAN"])
        need(
            all(layout[k] == v for k, v in evaluation.items()) and regs == regions,
            "T2 layout replay",
        )
        selection = run_path(HERE / "selection.py")
        for tag in ("P97", "P106"):
            name, h, _ = SRC["SOURCES"][tag]
            root = traces / ("part-" + tag[1:]) / name
            if tag == "P106":
                before, journal, _, proof = SRC["Q"]["read_new"](root, h)
                need(
                    before["banks"]["lru"]["ordered_keys"] == service["selected"]
                    and bank["selection_sha256"] == proof["selection_sha256"],
                    "before second POST",
                )
            else:
                journal, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
            actual, bounds = selection["capture"](journal)
            need(
                actual == physical["selection"] and bounds == physical["journals"][tag]["bounds"],
                "actual FIFO",
            )
            need(
                P["markers"](journal) == pipe["arms"][tag]["markers"]
                and K["service"](journal, regs[tag]) == service["journals"][tag],
                "original region clocks",
            )
        if derived:
            found, journals, records, packed = selection["plan"](traces, derived)
            need(
                found == physical["selection"]
                and journals == physical["journals"]
                and canonical(records) == physical["records"]
                and packed["pack_sha256"] == physical["pack_sha256"],
                "real tensor slice locations",
            )
    need(not derived or traces, "derived verification needs source journals")
    return dict(
        physical_merge=measured["merged"],
        physical_promotion=measured["promotion"],
        composed={
            tag: v["fixed_trained"]["direct"]["8000000000"]["decision"]
            for tag, v in bank["arms"].items()
        },
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    for arg in ("raw-archive", "trace-archive", "derived-pack"):
        a.add_argument("--" + arg, type=Path)
    args = a.parse_args()
    print(
        json.dumps(review(args.raw_archive, args.trace_archive, args.derived_pack), sort_keys=True)
    )
