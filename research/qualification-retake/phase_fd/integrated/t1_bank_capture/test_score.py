import unittest
from collections import Counter, defaultdict
from itertools import permutations
from pathlib import Path
from runpy import run_path

m = run_path(str(Path(__file__).with_name("score.py")))


class Acquisition(unittest.TestCase):
    def test_cold_and_credit(self):
        a, b, c, d = (0, 3), (0, 4), (26, 6), (26, 7)
        offers = [(key, i, 1, None) for i, key in enumerate((a, a, b, a, c, d, a, b))]
        cold, events, stat, cut = m["maintain"](offers, 2)
        self.assertEqual(cut, 2)
        self.assertEqual(stat["cpu"]["mru_noop"], 1)
        self.assertEqual(stat["cpu"]["promotion"], 1)
        for start in permutations((a, b, c, d), 2):
            bank, found, _, _ = m["maintain"](offers, 2, start)
            self.assertEqual(cold, bank)
            self.assertLessEqual(len(found), len(events))
            self.assertGreaterEqual(len(found), len(events) - 2)
        self.assertEqual(len(m["maintain"](offers, 2, [a, b])[1]), len(events) - 2)

    def test_lazy_defers_until_real_demand_including_restore(self):
        a, b = (26, 3), (0, 4)
        ready = set()
        costs = {n: defaultdict(Counter) for n in ("lazy", "eager")}
        for phase, requests in (
            ("call5", [(a, "primary")]),
            ("call148", [(a, "ram"), (b, "primary")]),
            ("restore", [(a, "ram"), (b, "ram")]),
            ("decode", [(b, "ram")]),
        ):
            m["materialize"](phase, requests, ready, costs, lambda key: 1100)
        self.assertEqual(ready, {a, b})
        self.assertEqual(costs["lazy"]["call5"]["gguf_fd_bytes"], 0)
        self.assertEqual(costs["lazy"]["call148"]["bank_write_bytes_cuda"], m["PAY"])
        self.assertEqual(costs["lazy"]["restore"]["first_disk_for_bank_cpu"], 1)
        self.assertEqual(costs["lazy"]["restore"]["ram_cuda"], 1)
        self.assertEqual(costs["lazy"]["decode"]["ram_cpu"], 1)
        self.assertEqual(costs["eager"]["restore"]["gguf_fd_bytes"], 0)

    def test_reject_duplicate_consumer(self):
        k = (0, 2)
        ledger = {n: defaultdict(Counter) for n in ("lazy", "eager")}
        with self.assertRaises(ValueError):
            m["materialize"]("decode", [(k, "ram"), (k, "ram")], set(), ledger, lambda key: 1)

    def test_rates_round_up(self):
        self.assertEqual(m["minimum_bytes_per_second"](1, 3), 333333334)
        with self.assertRaises(ValueError):
            m["minimum_bytes_per_second"](1, 0)


if __name__ == "__main__":
    unittest.main()
