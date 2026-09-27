import unittest

from c17_thermal_recovery import select_contiguous_window


class IdleWindowTests(unittest.TestCase):
    def test_full_window_and_cadence_break(self):
        samples = [{"elapsed_s": i * 0.5} for i in range(601)]
        self.assertGreaterEqual(select_contiguous_window(samples)[-1]["elapsed_s"] -
                                select_contiguous_window(samples)[0]["elapsed_s"], 300)
        # An early lost interval remains in the raw history, while a new
        # complete five-minute segment can later qualify on its own merits.
        with_break = [{"elapsed_s": i * 0.5} for i in range(80)]
        with_break += [{"elapsed_s": 41 + i * 0.5} for i in range(601)]
        self.assertIsNotNone(select_contiguous_window(with_break))
        self.assertGreaterEqual(select_contiguous_window(with_break)[0]["elapsed_s"], 41)

    def test_recent_break_rejects_incomplete_segment(self):
        samples = [{"elapsed_s": i * 0.5} for i in range(601)]
        samples += [{"elapsed_s": 302 + i * 0.5} for i in range(599)]
        self.assertIsNone(select_contiguous_window(samples))


if __name__ == "__main__":
    unittest.main()
