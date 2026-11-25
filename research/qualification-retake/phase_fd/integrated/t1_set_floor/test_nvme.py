import copy
import importlib.util
import unittest
from pathlib import Path

sp = importlib.util.spec_from_file_location("nvme_set_test", Path(__file__).with_name("nvme.py"))
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)


def plan():
    return [
        dict(
            site=[1, 1, layer, 0],
            experts=[
                dict(
                    expert=2,
                    slot=17,
                    generation=3,
                    components=[2, 0, 1],
                    ranges=[[100, 20, 0, 4096], [4210, 20, 4096, 4096], [8590, 20, 8192, 4096]],
                )
            ],
        )
        for layer in (2, 4)
    ]


def logs(t):
    return [
        dict(
            site=group["site"],
            order_indices=[0],
            drain_ns=t + 25,
            release_cost_ns=t,
            jobs=[
                dict(
                    expert=2,
                    role="demand",
                    worker_id=5,
                    finish_ns=t + 20,
                    read_spans_ns=[[t, t + 6], [t + 8, t + 13], [t + 15, t + 19]],
                )
            ],
            read_worker_ns=15,
            floor_ns=15,
            longest_job_ns=15,
        )
        for group in plan()
    ]


class NVMePrices(unittest.TestCase):
    def test_match_plan_and_faults(self):
        original = plan()
        self.assertEqual(m.match_plan(plan(), original), {(2, 2), (4, 2)})
        for field, v in (("slot", 3), ("generation", 4), ("components", [0, 2, 1]), ("expert", 7)):
            changed = copy.deepcopy(original)
            changed[1]["experts"][0][field] = v
            with self.assertRaisesRegex(ValueError, "mismatch"):
                m.match_plan(changed, original)
        for index in range(4):
            changed = copy.deepcopy(original)
            changed[0]["experts"][0]["ranges"][0][index] += 1
            with self.assertRaisesRegex(ValueError, "ranges"):
                m.match_plan(changed, original)
        with self.assertRaisesRegex(ValueError, "wave identity"):
            m.match_plan(original[::-1], original)

    def test_intraworker_durations_ignore_absolute_epoch(self):
        a = m.price_log(plan(), logs(13))
        self.assertEqual(a, m.price_log(plan(), logs(8_400_000_000)))
        self.assertEqual(a[1]["logical_bytes"], 120)
        for key, value in (("expert", 85), ("role", "prefetch")):
            changed = logs(13)
            changed[0]["jobs"][0][key] = value
            with self.assertRaisesRegex(ValueError, "expert order"):
                m.price_log(plan(), changed)
        changed = logs(13)
        changed[0]["jobs"][0]["read_spans_ns"][1][0] -= 4
        with self.assertRaisesRegex(ValueError, "serial"):
            m.price_log(plan(), changed)
        changed = logs(13)
        changed[0]["read_worker_ns"] += 1
        with self.assertRaisesRegex(ValueError, "per-wave"):
            m.price_log(plan(), changed)


if __name__ == "__main__":
    unittest.main()
