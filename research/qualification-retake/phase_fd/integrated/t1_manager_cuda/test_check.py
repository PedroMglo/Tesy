"""All host interleavings of the five events and corrupt output/byte witnesses."""

import itertools
import struct
import unittest
from pathlib import Path
from runpy import run_path

api = run_path(str(Path(__file__).with_name("check.py")))
verify, scalar, component = (api[k] for k in ("verify_arm", "scalar", "component"))
old, new = (struct.pack("<32f", *([scalar(n)] * 32)) for n in (1, 2))
slots = b"".join(component(2 if s == 0 else 1, r, s) for r in range(3) for s in range(4))
bank = b"".join(component(1, r, 0) for r in range(3))
events = ("READER_RELEASED", "GRAPH_DONE", "CAPTURED", "OVERWRITTEN", "OBSERVER")


class Ordering(unittest.TestCase):
    def test_all_orders_and_read_values(self):
        for arm, output, token in (
            ("original", old, old[:4]),
            ("event", old, None),
            ("broken", new, None),
        ):
            accepted = 0
            for seq in itertools.permutations(events):
                try:
                    verify(arm, slots, bank, output, token, seq, old, new)
                except ValueError:
                    continue
                accepted += 1
                self.assertLess(seq.index("CAPTURED"), seq.index("OVERWRITTEN"))
                if arm == "broken":
                    self.assertLess(seq.index("OVERWRITTEN"), seq.index("READER_RELEASED"))
                if arm == "original":
                    self.assertLess(seq.index("READER_RELEASED"), seq.index("OBSERVER"))
                    self.assertLess(seq.index("OBSERVER"), seq.index("OVERWRITTEN"))
                if arm == "event":
                    self.assertLess(seq.index("GRAPH_DONE"), seq.index("OVERWRITTEN"))
                with self.assertRaisesRegex(ValueError, "complete"):
                    verify(arm, slots, bank, new if arm != "broken" else old, token, seq, old, new)
            self.assertGreater(accepted, 0)

    def test_oracle_faults(self):
        seq = ("CAPTURED", "READER_RELEASED", "OBSERVER", "OVERWRITTEN", "GRAPH_DONE")
        for bad_slots, bad_bank, token in (
            (slots[:-1], bank, old[:4]),
            (slots, b"X" + bank[1:], old[:4]),
            (slots, bank, new[:4]),
        ):
            with self.assertRaises(ValueError):
                verify("original", bad_slots, bad_bank, old, token, seq, old, new)
        nan = struct.pack("<f", float("nan")) + old[4:]
        with self.assertRaisesRegex(ValueError, "scalar"):
            verify("original", slots, bank, nan, nan[:4], seq, nan, new)


if __name__ == "__main__":
    unittest.main()
