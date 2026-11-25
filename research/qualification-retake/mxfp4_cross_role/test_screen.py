"""An independent row-major coordinate oracle for the native counter."""

import random
import subprocess
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
gate = run_path(HERE / "screen.py")


def encode(matrix, scales):
    parts = []
    for r, row in enumerate(matrix):
        parts.append(scales[r])
        parts.extend(a | b << 4 for a, b in zip(row[:16], row[16:], strict=True))
    return bytes(parts)


def oracle(matrices, scales, role):
    counts = defaultdict(Counter)
    gate, up, _ = matrices
    for r, row in enumerate(matrices[role]):
        for c, k in enumerate(row):
            key = scales[r], c // 16, row[c - 1] if c else 16
            if role == 1:
                key += (gate[r][c],)
            if role == 2:
                key += (gate[c][r], up[c][r])
            counts[key][k] += 1
    terms = Counter()
    for table in counts.values():
        terms[sum(table.values())] += 1
        for n in table.values():
            terms[n] -= 1
    return len(counts), {k: v for k, v in terms.items() if v}


class TestCrossRole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.bin = Path(cls.temp.name) / "count"
        subprocess.run(
            [
                str(gate["base"].COMPILER),
                *gate["base"].FLAGS,
                str(HERE / "count.cpp"),
                "-o",
                str(cls.bin),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_asymmetric_coordinates_and_signed_zero(self):
        rng = random.Random(9245)
        # A noisy but non-random partner keeps the coefficient oracle sensitive to a transpose bug.
        g = [[rng.choice((0, 8, 1, 2)) for _ in range(32)] for _ in range(32)]
        u = [[(g[r][c] + (r % 3)) % 16 for c in range(32)] for r in range(32)]
        d = [[(u[c][r] + g[c][r]) % 16 for c in range(32)] for r in range(32)]
        roles = (g, u, d)
        scales = [[100 + (r // 7 + i) % 2 for r in range(32)] for i in range(3)]
        data = b"".join(encode(roles[i], scales[i]) for i in (0, 2, 1))
        proc = subprocess.run([str(self.bin), "32"], input=data, capture_output=True, check=True)
        for i, (_, ctx, terms) in enumerate(gate["parse"](proc.stdout, 1024)):
            self.assertEqual((ctx, terms), oracle(roles, scales[i], i))
        for bad in (data[:-1], data + b"x"):
            self.assertNotEqual(
                subprocess.run([str(self.bin), "32"], input=bad, capture_output=True).returncode, 0
            )

    def test_constant_symbol_is_free_in_optimistic_bound(self):
        self.assertEqual(gate["directed_floor"]({}, 1024), 0)
        with self.assertRaisesRegex(ValueError, "mass balance"):
            gate["parse"](b"ROLE 0 1\nTERMS\n1024 1\nEND\n", 1024)


if __name__ == "__main__":
    unittest.main()
