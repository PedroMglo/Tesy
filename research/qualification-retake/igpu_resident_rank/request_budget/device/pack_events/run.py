"""Run or reopen the synthetic pack-event fixture in an exclusive output directory."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture
from grade import grade, need

HERE = Path(__file__).resolve().parent
PROTOCOL = "e596d1b3b28a702515a46649ea793f5cc6be206af4f37d3e227a114ede25159c"
EXPECTED = {
    "hidden": (12, 0, [0, 0]),
    "exposed": (9, 4, [4, 4]),
    "unknown-fence": (11, 4, [0, 6]),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    with path.open("x") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def run(out, source=None, receipt_sha256=None):
    out.mkdir(mode=0o700)
    rec = {"cases": {}, "raw_sha256": {}, "new_forward_count": 0}
    try:
        rec["sources"] = {
            name: sha(HERE / name) for name in ("run.py", "grade.py", "fixture.py", "protocol.md")
        }
        need(rec["sources"]["protocol.md"] == PROTOCOL, "protocol digest")
        if source:
            receipt = source / "receipt.json"
            need(sha(receipt) == receipt_sha256, "replay authority")
            old = json.loads(receipt.read_bytes())
            need(
                old["status"] == "PASS_SYNTHETIC_PACK_EVENTS" and old["sources"] == rec["sources"],
                "replay sources",
            )
        for case, (compute, unknown) in fixture.CASES.items():
            name = case + ".json"
            if source:
                path = source / name
                need(sha(path) == old["raw_sha256"][case], "raw digest " + case)
                raw = json.loads(path.read_bytes())
            else:
                path = out / name
                raw = fixture.capture(compute, unknown)
                save(path, raw)
            rec["raw_sha256"][case] = sha(path)
            result = grade(raw)
            rec["cases"][case] = result
            contract = (
                result["wall_ticks"],
                result["consumer_ready_blocked_ticks"],
                result["exposed_gain_interval_ticks"],
            )
            need(contract == EXPECTED[case], "frozen expectation " + case)
            need(
                (result["service_worker_ticks"], result["service_union_ticks"]) == (28, 7),
                "service " + case,
            )
        rec["status"] = "PASS_SYNTHETIC_PACK_EVENTS"
        if source:
            need(rec == old, "offline results")
    except Exception as error:
        rec.update(status="FAIL_PRESERVED", reason=f"{type(error).__name__}: {error}")
    save(out / "receipt.json", rec)
    return rec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    parser.add_argument("--replay-dir", type=Path)
    parser.add_argument("--receipt-sha256")
    args = parser.parse_args()
    if bool(args.replay_dir) != bool(args.receipt_sha256):
        parser.error("replay requires --replay-dir and --receipt-sha256 together")
    result = run(args.new_output_dir, args.replay_dir, args.receipt_sha256)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
