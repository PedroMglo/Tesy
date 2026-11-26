import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

m = run_path(str(Path(__file__).with_name("score.py")))


class Aliases(unittest.TestCase):
    def test_loss_before_later_slack_is_permanent(self):
        store = m["Retained"]()
        a, b, c = (0, 1), (0, 2), (0, 3)
        with patch.dict(store.trim.__globals__, FIXED=m["cost"](2, 0)):
            for k in (a, b, c):
                store.offer(k)
                store.trim(set(), 2)
            self.assertEqual(list(store.order), [b, c])
            store.trim({c}, 2)
            self.assertNotIn(a, store.order)
            store.offer(c)
            store.trim({c}, 2)
            self.assertEqual(len(store.order), 2)

    def test_layer_identity_and_unique_physical_pages(self):
        same = (2, 1)
        other_cpu = (3, 1)
        gpu = (26, 1)
        self.assertEqual(m["intersection_keys"]([same, same, other_cpu, gpu], {same, gpu}), {same})
        step = m["WINDOW"]
        self.assertEqual(m["cost"](353, 0) - m["PADDING"], m["FIXED"])
        self.assertEqual(m["cost"](353, 0) - m["cost"](353, 1), step)
        self.assertEqual(m["layer_counts"]({same, gpu}, {same, other_cpu, gpu})[26], 1)

    def test_oracle_cannot_claim_future_offer(self):
        existing, offered, future = (1, 5), (25, 5), (3, 6)
        stats = m["oracle"](
            {"all": Counter({future: 100, existing: 3, offered: 2})},
            {existing, offered},
            {existing},
            set(),
            m["cost"](354, 0),
        )
        self.assertEqual((stats["all"]["free_jobs"], stats["all"]["paid_jobs"]), (3, 2))


if __name__ == "__main__":
    unittest.main()
