import itertools
import unittest
from pathlib import Path
from runpy import run_path

m = run_path(str(Path(__file__).with_name("screen.py")))
paid = run_path(m["ORACLE"])["paid_minimum"]


def brute(waves, capacity, initial, backed):
    costs = {frozenset(initial): 0}
    for wave in waves:
        pins = set(wave)
        new = {}
        for resident, prior in costs.items():
            price = prior + len(pins - resident - backed)
            for n in range(min(capacity - len(pins), len(resident - pins)) + 1):
                for keep in itertools.combinations(resident - pins, n):
                    state = frozenset(pins | set(keep))
                    new[state] = min(new.get(state, 10**5), price)
        costs = new
    return min(costs.values())


class OracleTests(unittest.TestCase):
    def test_paid_pins_and_terminal_against_exhaustive(self):
        choices = ([0], [1], [2], [0, 1], [0, 2], [1, 2])
        for seq in itertools.product(choices, repeat=3):
            for end in ([], [0, 2]):
                wave = list(seq) + ([end] if end else [])
                for backed in ({1}, {0, 1}, set()):
                    with self.subTest(wave=wave, backed=backed):
                        self.assertEqual(
                            paid(wave, 2, {0, 2}, backed), brute(wave, 2, {0, 2}, backed)
                        )
        with self.assertRaises((ValueError, RuntimeError)):
            paid([[0, 0]], 2, {0}, {1})

    def test_cuts_charge_for_repair_and_free_terminal(self):
        cells = [[[[0, 1]]], [[[1, 2]]], [[[2]]]]
        snapshots = [[{0, 1}], [{0, 1}], [{1, 2}], [{0, 2}]]
        table, cases = m["enumerate_cuts"](cells, snapshots, [set()], 2, paid)
        self.assertEqual(cases["external_sets_fixed"], [2])
        self.assertEqual(cases["return5_fixed_terminal_free"], [1])
        self.assertEqual(table[(2,)], cases["external_sets_fixed"])
        self.assertEqual(cases["no_required_exit"], [1])

    def test_paid_members_recovered_freely_from_bank(self):
        self.assertEqual(paid([[0, 1], [1, 2], [0, 1]], 2, {0, 1}, {0}), 1)
        self.assertEqual(paid([[0, 1], [1, 2], [0, 1]], 2, {0, 1}, set()), 2)


if __name__ == "__main__":
    unittest.main()
