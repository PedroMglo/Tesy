import unittest

from service_margin import PPM, Model, first_crossing, min_by_job


class ServiceMarginTests(unittest.TestCase):
    def test_first_discrete_crossing_and_unreachable_gate(self):
        self.assertEqual(first_crossing(lambda n: 0 if n >= 61785 else -1), 61785)
        self.assertEqual(first_crossing(lambda n: n), 0)
        self.assertEqual(first_crossing(lambda n: n - PPM), PPM)
        self.assertIsNone(first_crossing(lambda n: n - PPM - 1))

    def test_round_down_each_service_before_worker_sum(self):
        model = Model()
        keys = [(9, 0, 0, -1, k, "demand") for k in range(4)]
        model.capture(9, [0, 20], [0], [0], [(0, 1, 7)] * 4, keys, 20)
        base = model.evaluate("fixed_nonwait")
        scaled = model.evaluate("fixed_nonwait", 500_000)
        self.assertEqual((base["retained_worker_us"], scaled["retained_worker_us"]), (28, 12))
        self.assertEqual(scaled["ceiling_us"], 18)
        with self.assertRaisesRegex(ValueError, "outside freeze"):
            model.evaluate("fixed_nonwait", PPM + 1)

    def test_matching_uses_identity_instead_of_row_order(self):
        self.assertEqual(min_by_job([{"a": 2, "b": 9}, {"b": 3, "a": 7}]), {"a": 2, "b": 3})
        with self.assertRaisesRegex(ValueError, "different logical"):
            min_by_job([{"a": 1}, {"b": 1}])

    def test_duplicate_job_refused(self):
        model = Model()
        with self.assertRaisesRegex(ValueError, "duplicate retained"):
            model.capture(9, [0, 8], [0], [0], [(0, 1, 4)] * 2, ["x", "x"], 8)


if __name__ == "__main__":
    unittest.main()
