import importlib.util
import struct
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().with_name("build.py")
spec = importlib.util.spec_from_file_location("fusion_numerical_build", PATH)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class TestNumerical(unittest.TestCase):
    def fixture(self, mode, words, branch=0):
        data = struct.pack("<" + "I" * len(words), *words)
        case = dict(
            id="tiny",
            offset=0,
            bytes=len(data),
            expected_fusions=int(mode == "fusion"),
            observed_fusions=branch,
        )
        row = dict(
            status="PASS_NUMERIC_PARKED_FUSION_FIXTURE",
            mode=mode,
            cases=[case],
            total_bytes=len(data),
            fused_regions=branch,
        )
        return row, data

    def test_bitwise_and_observed_branch(self):
        a, gold = self.fixture("original", (0, 0x80000000, 1))
        orig = build.checked_parts(a, gold, "original")
        b, _ = self.fixture("fusion", (0, 0x80000000, 1), 1)
        same = build.checked_parts(b, gold, "fusion")
        self.assertIsNone(build.compare_cases(same, gold, orig, gold, "fusion"))
        for bits, reason in (((0, 0, 1), "output_bits"), ((0, 0x7FC00000, 1), "nonfinite")):
            b, d = self.fixture("fusion", bits, 1)
            failure = build.compare_cases(
                build.checked_parts(b, d, "fusion"), d, orig, gold, "fusion"
            )
            self.assertEqual((failure["reason"], failure["f32_index"]), (reason, 1))
        b, d = self.fixture("fusion", (0, 0x80000000, 1), 0)
        failure = build.compare_cases(build.checked_parts(b, d, "fusion"), d, orig, gold, "fusion")
        self.assertEqual(failure["reason"], "branch")

    def test_regions_exactly_partition_rows_and_counter(self):
        a, b = self.fixture("original", (0, 1))
        case = a["cases"][0]
        for changes in (
            {"cases": [case, case]},
            {"cases": [case | {"offset": 4}]},
            {"total_bytes": 12},
            {"fused_regions": 1},
            {"cases": [case | {"bytes": 4}]},
        ):
            with self.assertRaises(ValueError):
                build.checked_parts(a | changes, b, "original")


if __name__ == "__main__":
    unittest.main()
