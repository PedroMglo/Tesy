"""Negative controls on the released real observations. No model or raw PFJ needed."""

import copy
import gzip
import json
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "layer_release.py")
T, G = L["T"], L["G"]


class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = json.loads(
            gzip.decompress((HERE / "evidence-layer-20261128-r01/reads.json.gz").read_bytes())
        )
        cls.spans, cls.jobs = T["workload"]()

    def test_changed_greedy_router_record(self):
        ranks = copy.deepcopy(self.observations["plan"]["ranks"])
        word = ranks[0][1][0].to_bytes(4, "little")
        ranks[0][1][0] = int.from_bytes(bytes((word[1], word[0], word[2], word[3])), "little")
        with self.assertRaisesRegex(ValueError, "ordered router hash"):
            L["regroup"](self.spans["P97"], self.jobs, ranks)

    def test_unknown_generation_at_router(self):
        jobs = self.jobs.copy()
        part, group, ix, layer, _ = jobs[0]
        jobs[0] = (part, group, ix, layer, 128)
        with self.assertRaisesRegex(ValueError, "not revealed"):
            L["regroup"](self.spans["P106"], jobs, self.observations["plan"]["ranks"])

    def test_swapped_physical_groups(self):
        lines = self.observations["stdout"].splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        with self.assertRaisesRegex(ValueError, "population or clock"):
            T["parse"](lines, self.observations["plan"])

    def test_device_volume_deficit(self):
        data = copy.deepcopy(self.observations)
        data["physical"]["disk_delta"]["read_sectors_512B"] = (
            data["physical"]["requested_B"] - 1
        ) // 512
        jobs = L["regroup"](self.spans["P97"], self.jobs, data["plan"]["ranks"])
        with self.assertRaisesRegex(ValueError, "device, scope or byte receipt"):
            G["verify_reads"](data, jobs)


if __name__ == "__main__":
    unittest.main()
