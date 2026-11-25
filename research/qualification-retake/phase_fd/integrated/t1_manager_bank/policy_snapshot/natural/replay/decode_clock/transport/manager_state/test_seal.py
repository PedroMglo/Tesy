import unittest
from pathlib import Path
from runpy import run_path

seal = run_path(Path(__file__).with_name("seal.py"))


class ManagerStateTests(unittest.TestCase):
    def test_same_slot_on_another_generation_is_rejected(self):
        row = dict(expert=4, slot=1, generation=3, source="bank", ordinal=0)
        job = [(4, 1, 3, 2, 0)]
        seal["admissions_match"](job, [row], {4})
        for field, value in (("slot", 2), ("generation", 2), ("ordinal", 1), ("source", "disk")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                seal["admissions_match"](job, [row | {field: value}], {4})

    def test_import_keeps_ranked_hits_and_rejects_a_claimed_slot(self):
        bank = [set() for _ in range(36)]
        pools = [
            dict(
                age=[0] * 40, frequency=[0] * 128, clock=1, slots=[[e, 1, 2, 0] for e in range(40)]
            )
            for _ in bank
        ]
        cut = dict(pools=pools, remap_calls=2, decay_interval=2304)
        manager = seal["import_cut"](cut, bank)
        self.assertEqual(cut, seal["export_cut"](manager))
        ranks = [5, 4, 6, 8]
        self.assertEqual(manager.callback(1, -1, ranks), ([], [(e, e, 1) for e in ranks]))
        pools[1]["slots"][0][-1] = 1
        with self.assertRaisesRegex(ValueError, "undrained"):
            seal["import_cut"](cut, bank)


if __name__ == "__main__":
    unittest.main()
