import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

screen = run_path(str(Path(__file__).with_name("screen.py")))


def event(kind, time, tile=-1, layer=-1):
    return SimpleNamespace(kind=kind, ns=time, call=75, tile=tile, layer=layer)


class PipelineBounds(unittest.TestCase):
    def test_no_transition_uncertainty(self):
        # Artificial example in abstract ticks, ten per A and two per B.
        rows = [event(1, 0)]
        for i in range(5):
            t = i + 1
            rows.extend(
                [
                    event(3, i * 12, t),
                    event(9, i * 12, t, 0),
                    event(23, i * 12 + 10, t, 24),
                    event(9, i * 12 + 10, t, 25),
                    event(23, i * 12 + 12, t, 35),
                    event(4, i * 12 + 12, t),
                ]
            )
        rows.append(event(2, 60))
        self.assertEqual(screen["host_bounds"](rows, 75)["wall_cap_ns"], 8)
        for r in rows:
            if r.layer == 35 and r.tile != 5:
                r.layer = 34
        wider = screen["host_bounds"](rows, 75)
        self.assertEqual(wider["last_observed_layer"], [34, 34, 34, 34, 35])
        self.assertEqual(wider["wall_cap_ns"], 8)

    def test_disk_and_gap_share_one_credit(self):
        arm = {
            "47": {
                "victims": {
                    "prefill_payload_s": 3,
                    "envelope_s": 10,
                    "excess_s_at_6": 7 + 47 / 6 - 10,
                }
            }
        }
        gaps = {"protected_ns": 1_000_000_000, "eligible_cap_ns": 3_000_000_000}
        bound = screen["combined"](arm, gaps)["47"]["victims"]
        self.assertEqual(bound["min_prefill_s"], 4)
        self.assertAlmostEqual(bound["remaining_excess_s_at_6"], 4 + 47 / 6 - 10)


if __name__ == "__main__":
    unittest.main()
