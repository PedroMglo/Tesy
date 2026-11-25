import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

m = run_path(str(Path(__file__).with_name("plan.py")))


def row(kind, wave, expert=4):
    return SimpleNamespace(
        kind=kind, call=2, tile=1, layer=0, wave=wave, expert=expert, ns=10 + kind
    )


class Coverage(unittest.TestCase):
    def test_original_markers(self):
        rows = [row(9, 1), row(23, 1), row(9, 2), row(10, 2), row(23, 2)]
        remaps = list(m["remaps"](rows))
        self.assertEqual([r[3] for r in remaps], [[], [4]])
        for bad in (rows[:-1], rows + rows, rows[:4] + [row(23, 3)]):
            with self.assertRaises(ValueError):
                list(m["remaps"](bad))

    def test_timing_ambiguity(self):
        region = m["region"]
        f = 8_000_000
        self.assertEqual(region(1, 1, 2, f), "call5")
        self.assertEqual(region(2, 5, 9, f), "call148")
        self.assertEqual(region(3, 1, f - 1_000_001, f), "decode_before")
        self.assertEqual(region(3, 1, f - 1_000_000, f), "decode_boundary")
        self.assertEqual(region(4, f + 1_000_000, f + 2_000_001, f), "decode_boundary")
        self.assertEqual(region(4, f + 1_000_001, f + 2_000_001, f), "decode_after")

    def test_equal_is_not_equal_cost(self):
        c = m["bucket"]
        self.assertEqual(c(([], [])), ("identical", "empty"))
        self.assertEqual(c((["primary"], ["primary"])), ("identical", "0"))
        self.assertEqual(c((["disk"], ["disk"])), ("identical", "1"))
        self.assertEqual(c((["disk", "ram"], ["ram", "disk"])), ("equal_count", "2-4"))
        self.assertEqual(c((["disk"], ["primary"])), ("fewer", "1"))
        self.assertEqual(c((["primary"], ["disk"])), ("more", "1"))
        self.assertEqual(c((["ram"] * 5, ["ram"] * 5)), ("identical", "5+"))

    def test_design_and_bytes(self):
        sites = [(2, 1, 1, i) for i in range(8)]
        self.assertEqual(min(sites, key=m["digest"]), min(reversed(sites), key=m["digest"]))
        raw = m["counts"](
            1,
            [4, 8],
            (["ram", "disk"], ["disk", "primary"]),
            lambda layer, e: {"gguf": [{"count": e * 4096}] * 3},
            80,
        )
        self.assertEqual(raw["lru_ram_gguf_fd_bytes"], 8 * 4096 * 3)
        self.assertEqual(raw["evict_backed_first_gguf_fd_bytes"], 4 * 4096 * 3)
        self.assertEqual(raw["lru_ram_pack_fd_bytes"], raw["evict_backed_first_pack_fd_bytes"])
        for policy in m["POLICIES"]:
            self.assertEqual(sum(raw[policy + "_" + n] for n in ("primary", "ram", "disk")), 2)
        self.assertEqual(
            m["counts"](1, [], ([], []), lambda layer, e: None, 80), Counter(waves=1, consumers=0)
        )


if __name__ == "__main__":
    unittest.main()
