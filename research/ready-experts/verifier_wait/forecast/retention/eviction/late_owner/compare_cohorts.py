"""Identify exactly which priced prefill reads the online policy and the 120B fixture share."""

import argparse
import gzip
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(HERE / "causal.py")
OBS, SRC, need = C["OBS"], C["SRC"], C["need"]
METHOD = "76c24eed542af3c3e6183e0e91d5f27cce160d5cecc0a494be7def176eb13193"


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def generations(archive, sources):
    both = None
    for tag, digest in sources.items():
        name, outer, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            path = root / "ON/observer/events.pfj"
            _, rows, _, _ = SRC["Q"]["read_new"](root, outer)
        else:
            path = root / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        keys = [list(SRC["key"](r)) for r in rows if r.kind == 11 and r.call == 2]
        need(C["sha"](path) == digest and (both is None or keys == both), "source and reservations")
        both = keys
    need(len(both) == len(set(map(tuple, both))) == 1212, "unique generations")
    return both


def price_waits(waits, keys):
    gains = [OBS["cut_price"](w[1:], keys) for w in waits]
    return {"advanced_waits": sum(v > 0 for v in gains), "fixed_peers_ns": sum(gains)}


def compare(root, ordered, waits):
    raw = unpack(root / "causal-input.json.gz")
    scores = json.loads((root / "causal-grade.json").read_bytes())["policy"]
    arms = unpack(root / "arms.json.gz")
    captures = {v[0] for v in arms[1]["captures"]}
    C["need"](arms[1]["mode"] == "V" and len(captures) == 69, "physical source plan")
    result = {}
    for tag, arm in raw["arms"].items():
        jobs = []
        for op, value in arm["events"]:
            if op == 1:
                call = value
            elif op == 11:
                jobs.append((call, value))
        prefill = {i: value for i, (call, value) in enumerate(jobs, 1) if call == 2}
        fixture = {i for i, value in prefill.items() if value in captures}
        late = {i for i, value in prefill.items() if value == 14 * 128 + 54}
        C["need"](len(prefill) == 1212 and len(fixture) == 70 and len(late) == 1, "charged cohort")
        by_job = dict(zip(prefill, map(tuple, ordered), strict=True))
        need(all(128 * k[0] + k[3] == prefill[i] for i, k in by_job.items()), "source identity")
        ws = waits["traces"][tag]["waits"]
        result[tag] = {"physical": price_waits(ws, {by_job[i] for i in fixture})}
        for cap in (69, 353):
            bank = C["Bank"](cap, True)
            bank.replay(raw["t1"], training=True)
            hits, _ = bank.replay(arm["events"])
            score = scores[f"frequency_{cap}"]["arms"][tag]
            C["need"](C["IV"]["digest"](sorted(hits)) == score["hits_sha256"], "online decisions")
            actual = hits & prefill.keys()
            result[tag][str(cap)] = dict(
                online=len(actual),
                physical=len(fixture),
                shared=len(actual & fixture),
                physical_only=len(fixture - actual),
                online_only=len(actual - fixture),
                online_serves_late_54=late <= actual,
                **price_waits(ws, {by_job[i] for i in actual}),
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--new-output-dir", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    e = args.evidence
    need(bool(args.archive) == bool(args.new_output_dir), "paired raw input and fresh output")
    need(C["sha"](HERE / "cohort-audit.md") == METHOD, "cohort audit protocol")
    need(
        C["sha"](e / "waits.json.gz")
        == "11a4e1396c185ae7e7e3f720e14e2aad4c83867979451e7032c1e69f84f05592",
        "wait source",
    )
    waits = unpack(e / "waits.json.gz")
    if args.new_output_dir:
        out = args.new_output_dir
        out.mkdir()
        try:
            keys = generations(args.archive, waits["sources"])
            grade = compare(e, keys, waits)
            C["save"](out / "generations.json.gz", keys)
            C["save"](out / "overlap.json", grade)
        except Exception as exc:
            missing = (
                isinstance(exc, FileNotFoundError)
                and exc.filename is not None
                and Path(exc.filename).resolve().is_relative_to(args.archive.resolve())
            )
            C["save"](
                out / "failure.json",
                {
                    "status": "NOT_RUN_RAW_REQUIRED" if missing else "FAIL",
                    "reason": repr(exc),
                },
            )
            raise
    else:
        expected = json.loads((e / "overlap.json").read_bytes())
        need(compare(e, unpack(e / "generations.json.gz"), waits) == expected, "overlap audit")
        print("PASS causal hits, physical hits and conditional barrier times")


if __name__ == "__main__":
    main()
