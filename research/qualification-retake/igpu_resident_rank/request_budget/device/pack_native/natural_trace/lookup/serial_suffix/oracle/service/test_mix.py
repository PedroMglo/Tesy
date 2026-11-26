import itertools
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("mix.py")))


class MixedProof(unittest.TestCase):
    def test_bound_valid_for_all_integer_banks_and_invalid_mix_rejected(self):
        E = M["S"]["Event"]
        events = [
            E(98, frozenset({0, 1}), ((0, 74), (1, 40), (5, 43)), "prefill"),
            E(95, frozenset({1, 2}), ((1, 55), (2, 66), (4, 48)), "prefill"),
            E(73, frozenset({0, 2, 3}), ((3, 53), (6, 19), (6, 12)), "decode_first"),
            E(17, frozenset({2}), (), "decode_first"),
        ]
        offered = set(range(4))
        for cap, scale in ((1, 0), (2, 500_000), (2, 1_000_000)):
            opts = M["options"](events, offered, {0, 2}, scale)
            proof = M["propose"](opts, cap)
            actual = max(
                M["S"]["exact"](M["S"]["cost_rows"](events, set(b), offered)[0], scale)
                for b in itertools.combinations(offered, cap)
            )
            self.assertGreaterEqual(M["certify"](opts, proof, cap), actual)
            mix = []
            for i, variants in enumerate(opts):
                row = [0] * len(variants)
                row[i % len(row)] += 1
                row[0] += M["MIX"] - 1
                mix.append(row)
            weights = M["weights"](opts, mix)
            self.assertGreaterEqual(
                M["certify"](opts, {"mix": mix, "shares": [v // 2 for _, v in weights]}, cap),
                actual,
            )
            proof["mix"][0][0] += 1
            with self.assertRaises(ValueError):
                M["certify"](opts, proof, cap)


if __name__ == "__main__":
    unittest.main()
