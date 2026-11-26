import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().with_name("run.py")
spec = importlib.util.spec_from_file_location("b3_fixture_control", PATH)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class TestReference(unittest.TestCase):
    def test_classes_and_boundaries(self):
        rule = control.python_rule()
        prompt = [90, 1, 2, 3, 4, 80, 1]
        for target, count, match, wrong, cut, discarded in (
            ([2, 8, 7, 9], 3, 0, True, False, 2),
            ([2, 3, 8, 9], 3, 1, True, False, 1),
            ([2, 3, 4, 8], 3, 2, False, False, 0),
            ([2, 3, 4, 8], 1, 1, False, True, 1),
            ([2, 3, 4, 8], 2, 2, False, True, 0),
        ):
            row = control.trace(rule, prompt, target, count)[0]
            self.assertEqual(
                (
                    row["accepted_draft"],
                    row["mismatch"],
                    row["boundary_interrupted"],
                    row["discarded_draft"],
                ),
                (match, wrong, cut, discarded),
            )
            self.assertEqual(row["beyond_window_rows"], 0)

    def test_censoring_is_independent_of_future(self):
        rule = control.python_rule()
        prompt = [90, 1, 2, 3, 4, 80, 1]
        self.assertEqual(
            control.trace(rule, prompt, [2, 3, 8], 1), control.trace(rule, prompt, [2, 3, 4, 9], 1)
        )
        with self.assertRaises(ValueError):
            control.trace(rule, prompt, [2, 3], 2)
