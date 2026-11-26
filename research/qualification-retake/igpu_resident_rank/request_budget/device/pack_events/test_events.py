import argparse
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture
import grade
import run


def refutations(base):
    for name, kind in (
        ("stale_publish", "PUBLISH"),
        ("missing_role", "SET_END"),
        ("duplicate_claim", "SKIP_DUPLICATE"),
    ):
        raw = copy.deepcopy(base)
        rows = raw["records"]
        event = next(e for e in rows if e["kind"] == kind)
        if name == "stale_publish":
            event["key"][3] += 1
        elif name == "missing_role":
            rows.remove(event)
            for n, row in enumerate(rows):
                row["n"] = n
            raw["saved"] = len(rows)
        else:
            event["kind"] = "CLAIM"
        yield name, raw


def preserve_faults(source, sha256, out):
    out.mkdir(mode=0o700)
    rec = {"status": "FAIL_PRESERVED", "source_sha256": sha256, "faults": {}}
    try:
        if run.sha(source / "receipt.json") != sha256:
            raise ValueError("source digest")
        prior = json.loads((source / "receipt.json").read_bytes())
        if (
            prior["status"] != "PASS_SYNTHETIC_PACK_EVENTS"
            or run.sha(source / "exposed.json") != prior["raw_sha256"]["exposed"]
        ):
            raise ValueError("raw authority")
        positive = json.loads((source / "exposed.json").read_bytes())
        if grade.grade(positive) != prior["cases"]["exposed"]:
            raise ValueError("positive control")
        for name, data in refutations(positive):
            path = out / (name + ".json")
            run.save(path, data)
            try:
                grade.grade(data)
            except ValueError as error:
                rec["faults"][name] = {
                    "status": "REJECTED",
                    "reason": str(error),
                    "sha256": run.sha(path),
                }
            else:
                raise ValueError("accepted mutation " + name)
        rec["status"] = "PASS_THREE_REJECTIONS"
    except Exception as error:
        rec["reason"] = str(error)
    run.save(out / "receipt.json", rec)
    return rec


class PackEvents(unittest.TestCase):
    def test_compute_crosses_delivery(self):
        for c in (1, 3, 7, 8, 10):
            with self.subTest(c=c):
                result = grade.grade(fixture.capture(c))
                self.assertEqual(result["exposed_gain_interval_ticks"], [max(0, 7 - c)] * 2)
                self.assertEqual(result["free_delivery_wall_interval_ticks"], [c + 2] * 2)
                self.assertEqual(result["read_worker_ticks"], 16)
                self.assertEqual(result["set_worker_ticks"], 12)

    def test_indistinguishable_completion(self):
        r = grade.grade(fixture.capture(3, 9))
        self.assertEqual(r["status"], "BOUNDED_UNKNOWN_FENCE")
        self.assertEqual(r["consumer_ready_blocked_ticks"], 4)
        self.assertEqual(r["free_delivery_wall_interval_ticks"], [5, 11])
        self.assertEqual(r["exposed_gain_interval_ticks"], [0, 6])

    def test_bad_generation_role_and_duplicate(self):
        base = fixture.capture(3)
        for mutation in ("stale", "role", "duplicate", "tid", "order", "truncated", "unknown"):
            with self.subTest(mutation=mutation):
                raw = copy.deepcopy(base)
                rows = raw["records"]
                if mutation == "stale":
                    next(e for e in rows if e["kind"] == "PUBLISH")["key"][-1] += 1
                elif mutation == "role":
                    next(e for e in rows if e["kind"] == "SET_END")["sha256"] = "0" * 64
                elif mutation == "duplicate":
                    next(e for e in rows if e["kind"] == "SKIP_DUPLICATE")["kind"] = "CLAIM"
                elif mutation == "tid":
                    next(e for e in rows if e["kind"] == "READ_END")["tid"] = raw["host_tid"]
                elif mutation == "order":
                    rows[-1]["t"] = 0
                elif mutation == "truncated":
                    raw["dropped"] = 1
                else:
                    raw["visibility"] = "assumed"
                with self.assertRaises(ValueError):
                    grade.grade(raw)

    def test_preserve_failed_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            src = p / "r1"
            self.assertEqual(run.run(src)["status"], "PASS_SYNTHETIC_PACK_EVENTS")
            authority = run.sha(src / "receipt.json")
            again = p / "r2"
            run.run(again, src, authority)
            self.assertEqual(
                (src / "receipt.json").read_bytes(), (again / "receipt.json").read_bytes()
            )
            raw = src / "exposed.json"
            raw.write_bytes(raw.read_bytes() + b" ")
            rejected = p / "bad"
            run.run(rejected, src, authority)
            result = json.loads((rejected / "receipt.json").read_bytes())
            self.assertEqual(result["status"], "FAIL_PRESERVED")
            self.assertEqual(list(result["cases"]), ["hidden"])
            with self.assertRaises(FileExistsError):
                run.run(rejected, src, authority)


if __name__ == "__main__":
    if "--source" in sys.argv:
        parser = argparse.ArgumentParser(description="Preserve the three synthetic counterexamples")
        parser.add_argument("--source", type=Path, required=True)
        parser.add_argument("--receipt-sha256", required=True)
        parser.add_argument("--new-output-dir", type=Path, required=True)
        args = parser.parse_args()
        result = preserve_faults(args.source, args.receipt_sha256, args.new_output_dir)
        print(result["status"], result.get("reason", ""))
        raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
    unittest.main()
