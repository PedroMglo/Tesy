import unittest
from pathlib import Path
from runpy import run_path

F = run_path(Path(__file__).with_name("frames.py"))


class OwnershipTests(unittest.TestCase):
    def test_source_and_capture_share_or_exchange_independent_frames(self):
        for src, dst, want in (
            (0, 0, [1, 0, 2]),
            (0, 1, [1, 2, 0]),
            (0, None, [1, 0, 2]),
            (None, 1, [2, 1, 0]),
            (None, None, [0, 1, 2]),
        ):
            a, b = [0], [1, 2]
            F["rebind"](a, b, 0, src, dst)
            self.assertEqual(a + b, want)

    def test_stale_component_and_duplicate_frame_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "component"):
            F["verify"]([(0, 1, 1), (3, 4, 5)], [0], [1], [0], [1])
        with self.assertRaisesRegex(ValueError, "frame"):
            F["verify"]([(0, 1, 2), (3, 4, 5)], [1], [1], [1], [1])


if __name__ == "__main__":
    unittest.main()
