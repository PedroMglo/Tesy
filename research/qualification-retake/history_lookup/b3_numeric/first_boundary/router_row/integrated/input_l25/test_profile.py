import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock

PATH = Path(__file__).with_name("profile.py")
SPEC = importlib.util.spec_from_file_location("l25_test_supervisor", PATH)
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class ProfileContract(unittest.TestCase):
    def test_prepare_pins_exact_arm_and_identity(self):
        ident = {"unit": "scope-on", "order": ["ON"], "build_sha256": "client"}
        prep = {
            "status": "PREPARED_ONLY",
            "identity": ident,
            "model_launch_receipts": 0,
            "arms": {"ON": {"status": "PREPARED_ONLY"}},
        }
        profile.check_prepared(prep, ident)
        for change in (
            {"identity": ident | {"build_sha256": "different"}},
            {"identity": ident | {"unit": "other"}},
            {"model_launch_receipts": 1},
            {"arms": prep["arms"] | {"OFF": {"status": "PREPARED_ONLY"}}},
            {"status": "FAIL_PRESERVED"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                profile.check_prepared(prep | change, ident)

    def test_references_and_neutrality_before_diagnosis(self):
        orig = {"AR": Path("baseline-ar"), "ON": Path("integrated-on")}
        c270, capture = Path("gold"), Path("new-on")
        prior = {"bitwise": False, "routers_with_gold": 86, "routers_equal": 64, "first": {}}
        report = {
            "status": "MEASURED_L25_INPUTS",
            "neutral": True,
            "diagnosis": {"189": "different"},
        }
        grader = Mock()
        grader.compare.return_value = report
        translate = profile.comparison_callback(orig, c270, prior, grader)
        result = translate(capture, "ON", orig["AR"], None, profile.OLD)
        grader.compare.assert_called_once_with(capture, orig["ON"], c270, orig["AR"])
        self.assertEqual(result, report | prior)
        for mode, ar, parent in (
            ("OFF", orig["AR"], profile.OLD),
            ("ON", orig["ON"], profile.OLD),
            ("ON", orig["AR"], None),
        ):
            with self.subTest(mode=mode, ar=ar), self.assertRaises(ValueError):
                translate(capture, mode, ar, None, parent)
        grader.compare.assert_called_once()
        for change in ({"neutral": False}, {"status": "FAIL_PRESERVED"}):
            grader.compare.return_value = report | change
            with self.assertRaises(ValueError):
                translate(capture, "ON", orig["AR"], None, profile.OLD)

    def test_observer_module_resolves_both_grades(self):
        grader = profile.load(PATH.with_name("grade.py"), "l25_test_extra_grade")
        self.assertEqual(Path(grader.__file__).resolve(), PATH.with_name("grade.py").resolve())
        self.assertEqual(
            Path(grader.base.__file__).resolve(), (PATH.parents[3] / "grade.py").resolve()
        )
        self.assertIs(profile.E.boundary, grader.base)


if __name__ == "__main__":
    unittest.main()
