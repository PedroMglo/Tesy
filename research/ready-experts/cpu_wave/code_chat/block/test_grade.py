"""Regression for comparing a rejected branch to the correct serial reference."""

import unittest
from pathlib import Path
from runpy import run_path


class RollbackComparison(unittest.TestCase):
    def test_kept_and_discarded_states_have_distinct_authorities(self):
        compare = run_path(Path(__file__).with_name("grade.py"))["compare"]

        def proof(branch, keep="confirmed", wrong="fixed"):
            return dict(
                values={
                    "1-branch.json": branch,
                    "1-keep.json": keep,
                    "1-next-0.f32": "next",
                    "1-row-1.f32": wrong,
                },
                service={},
                loads={},
            )

        reference = proof("speculative")
        serial = proof("serial")
        del serial["values"]["1-row-1.f32"]
        records = {"R": reference, "W": serial, "OFF": serial, "ON": proof("speculative")}
        self.assertTrue(all(compare(records, "ON").values()))
        records["ON"] = proof("serial", keep="stale", wrong="wrong branch row")
        observed = compare(records, "ON")
        self.assertFalse(observed["R/1-branch.json"])
        self.assertFalse(observed["R/1-row-1.f32"])
        self.assertFalse(observed["W/1-keep.json"])
        self.assertNotIn("W/1-branch.json", observed)


if __name__ == "__main__":
    unittest.main()
