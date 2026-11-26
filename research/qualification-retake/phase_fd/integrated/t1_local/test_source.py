import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "t1_local_source", Path(__file__).with_name("source.py")
)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class LocalBoundary(unittest.TestCase):
    def setUp(self):
        row = source.fd.Row(*([0] * len(source.fd.Row._fields)))
        self.prefix = [
            row._replace(kind=5, layer=layer, slot=slot, expert=-1)
            for layer in range(36)
            for slot in range(40)
        ]
        self.current = [(-1, 0, 0, 0)] * 1440

    def test_reconstructs_current_identity_independently_of_initial_order(self):
        self.current[41] = (27, 5, 2, 0)
        result = source.local_slots(self.prefix[::-1], self.current)
        r = result[41]
        self.assertEqual((r.layer, r.slot, r.expert, r.gen, r.a, r.b), (1, 1, 27, 5, 2, 0))

    def test_rejects_lost_slot_or_loading_claim_at_boundary(self):
        with self.assertRaisesRegex(ValueError, "all primary slots"):
            source.local_slots(self.prefix[:-1], self.current)
        self.current[41] = (27, 5, 1, 1)
        with self.assertRaisesRegex(ValueError, "undrained"):
            source.local_slots(self.prefix, self.current)
