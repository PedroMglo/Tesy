import copy
import importlib.util
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mxfp4_spatial_screen", HERE / "screen.py")
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class ScreenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.folder.name) / "test"
        subprocess.run(
            [
                str(screen.base.COMPILER),
                *screen.base.FLAGS,
                str(HERE / "count.cpp"),
                "-o",
                str(cls.binary),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_native_order_and_reset(self):
        def block(scale, codes):
            return bytes([scale, *(codes[i] | (codes[16 + i] << 4) for i in range(16))])

        blocks = [
            (3, list(range(16)) + [2] * 16),
            (5, [9] * 16 + [7] * 16),
            (3, [8] * 32),
            (5, [4] * 32),
        ]
        payload = b"".join(block(scale, codes) for scale, codes in blocks)

        def count(data):
            return subprocess.run([str(self.binary), "2"], input=data, capture_output=True)

        run = count(payload)
        self.assertEqual(run.returncode, 0)
        expected = Counter()
        marginal = {3: [0] * 16, 5: [0] * 16}
        for i, (scale, codes) in enumerate(blocks):
            if i % 2 == 0:
                prev = 16
            for pos, code in enumerate(codes):
                expected[(scale, pos // 16, prev, code)] += 1
                prev = code
                marginal[scale][code] += 1
        actual = {}
        for line in run.stdout.splitlines():
            s, h, p, *freq = map(int, line.split())
            actual.update({(s, h, p, c): v for c, v in enumerate(freq) if v})
        self.assertEqual(actual, dict(expected))
        joint = [[s, f] for s, f in marginal.items()]
        prior = {
            "joint_counts_sha256": screen.base.canonical_digest(joint),
            "scale_bits_floor": 0,
            "conditional_nibble_bits_floor": 0,
        }
        self.assertEqual(screen.analyse_hist(run.stdout, 4, 2, prior)["row_starts"], 2)
        with self.assertRaisesRegex(ValueError, "row resets"):
            screen.analyse_hist(run.stdout, 4, 1, prior)
        with self.assertRaisesRegex(ValueError, "joint mismatch"):
            screen.analyse_hist(run.stdout, 4, 2, dict(prior, joint_counts_sha256="no"))
        self.assertNotEqual(count(payload[:-1]).returncode, 0)

    def test_range_n_log(self):
        for n in (1, 2, 31, 16383, 16384, 16385, 30001, 1 << 20, 8_294_400):
            lo, hi = screen.n_log_n(n)
            exact_lo, exact_hi = screen.m.log2_bounds(n)
            self.assertLessEqual(lo, n * exact_lo)
            self.assertGreaterEqual(hi, n * exact_hi)

    def test_no_per_matrix_raw_choice(self):
        ws = [{"contexts": 1, "encoded_bytes_floor": v} for v in (5_000_000, 1, 1)]
        r = screen.expert_row(0, 2, "CPU", ws)
        self.assertEqual(r["aligned_bytes_floor"], screen.base.aligned(5_000_002, 4096))
        ws = copy.deepcopy(ws)
        ws[0]["encoded_bytes_floor"] = 55_000_000
        raw = screen.expert_row(0, 3, "CPU", ws)
        self.assertEqual(raw["aligned_bytes_floor"], screen.WINDOW)
        self.assertEqual(screen.summarize([r, raw])["experts_gate20_possible"], 1)


if __name__ == "__main__":
    unittest.main()
