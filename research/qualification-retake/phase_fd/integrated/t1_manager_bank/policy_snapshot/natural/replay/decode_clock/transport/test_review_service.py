import unittest
from copy import deepcopy
from pathlib import Path
from runpy import run_path

mod = run_path(str(Path(__file__).with_name("review_service.py")))


class TestPrice(unittest.TestCase):
    def setUp(self):
        self.plan = dict(step=0, position=2197, call=76, tile=1, layer=0, wave=-1, tier="CPU")
        identities = [dict(ordinal=i, expert=i, slot=i + 1, generation=4) for i in range(3)]
        weights = [
            dict(role=r, sha256=r, size_bytes=2, aligned_bytes=4) for r in ("gate", "down", "up")
        ]
        self.plan["jobs"] = [
            dict(
                **j,
                source="bank" if j["ordinal"] == 1 else "disk",
                components=weights,
                pack_bytes=8,
                r0_same_site_set_ns=s,
            )
            for j, s in zip(identities, (2, 9, 1), strict=True)
        ]
        self.obs = dict(
            self.plan,
            jobs=[
                dict(
                    **identities[i],
                    worker=i + 40,
                    component_sha256=["gate", "down", "up"],
                    read_spans_ns=[[i, i + 6]],
                )
                for i in (0, 2)
            ],
            read_worker_ns=12,
            read_union_ns=8,
            release_ns=0,
            drain_ns=9,
            hash_ns=11,
        )

    def test_bank_and_disk_overlap(self):
        c, workers = mod["group"](self.plan, self.obs, "P")
        self.assertEqual((c["read_floor"], c["common_set_floor"], c["set_only"]), (6, 9, 9))
        self.assertEqual((c["disk_jobs"], c["bank_jobs"], workers), (2, 1, {40, 42}))

    def test_payload_and_worker_identity(self):
        broken = deepcopy(self.obs)
        broken["jobs"][0]["component_sha256"].reverse()
        with self.assertRaises(ValueError):
            mod["group"](self.plan, broken, "P")
        broken = deepcopy(self.obs)
        broken["jobs"][1]["worker"] = 40
        with self.assertRaises(ValueError):
            mod["group"](self.plan, broken, "P")

    def test_overlapping_reads_distinct_and_empty(self):
        self.assertEqual(mod["union"]([[1, 4], [2, 6], [3, 5], [7, 9]]), 7)
        self.plan["jobs"] = self.plan["jobs"][1:2]
        self.obs.update(jobs=[], drain_ns=0, hash_ns=0, read_worker_ns=0, read_union_ns=0)
        c, _ = mod["group"](self.plan, self.obs, "P")
        self.assertEqual((c["disk_groups"], c["common_set_floor"]), (0, 9))


if __name__ == "__main__":
    unittest.main()
