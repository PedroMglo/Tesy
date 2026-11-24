"""Verify both preregistered C163-ON logical replays without GPU or weights."""

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from c152_journal_validate import validate  # noqa: E402
from c152_snapshot_read import routes, snapshot  # noqa: E402
from replay import need, replay  # noqa: E402

C163 = "c163-instrumentation-overhead-20260930T1145Z"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(raw, ledger, arm):
    need(
        sha(ledger / "raw-manifest.json")
        == "a6b594897e90c9e8571f1f3b5b858c2595dcbbf771db1e518ea59b5199d5f398"
        and sha(ledger / "protocol.json")
        == "f9d45c4a70613525a4c83379c1411c5d04fcc2e11de3991a05572086989f355a",
        "C163 ledger identity",
    )
    manifest = json.loads((ledger / "raw-manifest.json").read_text())["files"]
    protocol = json.loads((ledger / "protocol.json").read_text())
    runs = {entry["id"]: entry for entry in protocol["runs"]}
    env = runs[arm]["env"]
    hashes = [env["TESY_C152_" + tag + "_HASH"] for tag in ("MODEL", "SOURCE", "BUILD", "PROFILE")]
    names = [
        arm + suffix
        for suffix in (
            ".routes",
            ".trace.window.trace",
            ".capture/before-warm.snap",
            ".capture/after-prefill.snap",
            ".capture/calls.tsv",
        )
    ]
    for name in names:
        size, digest = (manifest[name][k] for k in ("bytes", "sha256"))
        need(
            (raw / name).stat().st_size == size and sha(raw / name) == digest,
            f"manifest mismatch {name}",
        )
    route_path, journal, first, last, calls = (raw / name for name in names)
    with calls.open() as stream:
        plan = list(csv.DictReader(stream, delimiter="\t"))
    need(
        [(r["call"], r["phase"], r["first"], r["last"]) for r in plan[8:10]]
        == [("9", "warm-prefill", "2044", "2048"), ("10", "warm-prefill", "2049", "2196")],
        "call plan",
    )
    initial, final = (snapshot(p, expected_hashes=hashes) for p in (first, last))
    need(
        [
            (s["request"], s["sequence"], s["phase"], s["call_id"], s["workers"])
            for s in (initial, final)
        ]
        == [(2, 0, 0, 8, 4), (2, 1, 1, 10, 4)],
        "invalid warm cut identity",
    )
    return (
        initial,
        final,
        validate(journal, initial=initial)["rows"],
        routes(route_path),
        {name: manifest[name] for name in names},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, default=ROOT / "results" / C163)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir()
    arm = None
    try:
        result = {
            "schema": "tesy-prefill44-replay-v1",
            "arms": {},
            "freeze_sha256": sha(Path(__file__).with_name("protocol.md")),
        }
        for arm in ("c163-on-1", "c163-on-2"):
            initial, final, rows, routing, files = inputs(args.raw_dir, args.evidence_dir, arm)
            result["arms"][arm] = {
                "inputs": files,
                "journal_cut_seq": [initial["transition_seq"], final["transition_seq"]],
                "replay": replay(initial, final, rows, routing),
            }
        # Faults operate on copies of ON1, after both original arms matched.
        from fault_checks import fault_checks

        original = inputs(args.raw_dir, args.evidence_dir, "c163-on-1")
        result["rejected_faults"] = fault_checks(*original[:4])
        pending = args.new_output_dir / ".receipt"
        with pending.open("x") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
        os.replace(pending, args.new_output_dir / "receipt.json")
    except Exception as exc:
        with (args.new_output_dir / "FAIL.json").open("x") as out:
            json.dump({"arm": arm, "failure": str(exc)}, out)
        raise


if __name__ == "__main__":
    main()
