import unittest

from c120_analyze import screen_decision
from c117_analyze import METRICS


class TestC120ScreenGate(unittest.TestCase):
    def test_protected_cold_prefill_blocks_good_primary(self):
        pairs = [{"gain_percent": {key: 10 for key in METRICS}} for _ in range(2)]
        self.assertTrue(screen_decision(pairs)[0])
        pairs[0]["gain_percent"]["cold_prefill_s"] = -6
        pairs[1]["gain_percent"]["cold_prefill_s"] = -6
        self.assertFalse(screen_decision(pairs)[0])
        pairs[0]["gain_percent"]["cold_prefill_s"] = -5
        pairs[1]["gain_percent"]["cold_prefill_s"] = -5
        self.assertTrue(screen_decision(pairs)[0])
        pairs[0]["gain_percent"]["warm_first_final_s"] = -1
        self.assertFalse(screen_decision(pairs)[0])


if __name__ == "__main__":
    unittest.main()
