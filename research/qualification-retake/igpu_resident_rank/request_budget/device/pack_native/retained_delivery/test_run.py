import unittest
from copy import deepcopy
from pathlib import Path
from runpy import run_path

R = run_path(str(Path(__file__).with_name("run.py")))


def sample(mode):
    freq = mode != "lru_bank"
    expected = [36, 38, 39] if freq else [37, 38, 39]
    hits = set(expected) if mode != "freq_disk" else set()
    gold = {"records": [{"role_sha256": [str((rec, i)) for i in range(3)]} for rec in range(6)]}
    stages = [(2, 36, 4), (2, 38, 5), (2, 39, 6), (2, 44, 7), (3, 37, 8)]
    terminal, bad = [], []
    for i, e in enumerate([40, 41, 42, 43, 36, 38, 39, 44, 37, *range(5, 36)]):
        source = 38 if mode == "wrong" and e == 36 else e
        h = gold["records"][max(0, min(5, source - 35))]["role_sha256"]
        terminal.append([i, e, 2 if i < 9 else 1, h])
        if e != source:
            bad.extend([i, e, k, item] for k, item in enumerate(h))
    jobs = []
    for phase, e, slot in stages:
        origin = 38 if mode == "wrong" and e == 36 else e
        jobs.append(
            dict(
                phase=phase,
                expert=e,
                slot=slot,
                generation=2,
                sets=3,
                preads=int(e not in hits),
                bank_expert=origin if e in hits else -1,
            )
        )
    return {
        "status": "COMPLETED_C291_RETAINED_DELIVERY",
        "mode": mode,
        "workers_joined": 4,
        "pack_extent": R["WIN"],
        "reads": [40, 4, 4 - len(hits & {36, 38, 39, 44}), int(37 not in hits)],
        "sets": [120, 12, 12, 3],
        "publications": [40, 4, 4, 1],
        "captures": [[36 + i, i, 1] for i in range(4)],
        "bank": {"ordered_keys": [[0, e] for e in expected], "copies": {"CPU": 4, "CUDA0": 0}},
        "terminal": terminal,
        "mismatches": bad,
        "work": jobs,
    }, gold


class Service(unittest.TestCase):
    def test_fault_and_work_conservation(self):
        for mode in R["ARMS"]:
            row, gold = sample(mode)
            self.assertEqual(R["verify"](mode, row, gold)["reads"], row["reads"])
            for table, key, value in [("work", "preads", 7), ("work", "generation", 1)]:
                bad = deepcopy(row)
                bad[table][0][key] = value
                with self.assertRaises(ValueError):
                    R["verify"](mode, bad, gold)
            bad = deepcopy(row)
            bad["terminal"][4][3][1] = "wrong component"
            with self.assertRaises(ValueError):
                R["verify"](mode, bad, gold)


if __name__ == "__main__":
    unittest.main()
