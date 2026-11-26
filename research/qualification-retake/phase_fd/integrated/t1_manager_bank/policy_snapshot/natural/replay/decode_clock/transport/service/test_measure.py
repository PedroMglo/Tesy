import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

d = run_path(str(Path(__file__).with_name("measure.py")))


class ReadService(unittest.TestCase):
    def test_two_layouts_preserve_jobs_and_hashes(self):
        unit = bytes(range(24))
        jobs = [
            {
                "source": source,
                "ordinal": ordinal,
                "expert": ordinal,
                "generation": 3,
                "slot": ordinal,
                "pack_offset": 0,
                "components": [
                    {
                        "aligned_offset": i * 8,
                        "aligned_bytes": 8,
                        "source_offset": i * 8,
                        "packed_relative_offset": i * 8,
                        "sha256": hashlib.sha256(unit[i * 8 : i * 8 + 8]).hexdigest(),
                    }
                    for i in range(3)
                ],
            }
            for ordinal, source in enumerate(("disk", "bank", "disk", "disk"))
        ]
        g = dict(step=0, position=2197, call=76, tile=1, layer=0, wave=-1, tier="CPU", jobs=jobs)
        with (
            patch.dict(d["group_read"].__globals__, SIZE=8, CHUNK=4096, WINDOW=24),
            ExitStack() as s,
        ):
            buf = d["arena"](s)
            f = s.enter_context(tempfile.TemporaryFile())
            f.write(unit)
            f.flush()
            pool = s.enter_context(ThreadPoolExecutor(max_workers=4))
            for layout, calls in (("R", 3), ("P", 1)):
                row, volume = d["group_read"](pool, f.fileno(), buf, layout, g)
                self.assertEqual(volume, 72)
                self.assertEqual([j["ordinal"] for j in row["jobs"]], [0, 2, 3])
                self.assertEqual([len(j["read_spans_ns"]) for j in row["jobs"]], [calls] * 3)
                self.assertLessEqual(row["read_union_ns"], row["drain_ns"])
            jobs[0]["components"][1]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                d["group_read"](pool, f.fileno(), buf, "P", g)


if __name__ == "__main__":
    unittest.main()
