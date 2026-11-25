import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

module = run_path(str(Path(__file__).with_name("measure.py")))
measure = module["queued_call"]


class PrefillQueue(unittest.TestCase):
    def test_fifo_counts_integrity_and_followup_call(self):
        payload = bytes(range(24))
        components = [
            dict(
                aligned_offset=i,
                aligned_bytes=8,
                source_offset=i,
                packed_relative_offset=i,
                sha256=hashlib.sha256(payload[i : i + 8]).hexdigest(),
            )
            for i in (0, 8, 16)
        ]
        with ExitStack() as stack:
            for fn in (measure, module["ref"]["ranges"]):
                stack.enter_context(patch.dict(fn.__globals__, SIZE=8, CHUNK=4096, WINDOW=24))
            buffers = module["ref"]["arena"](stack)
            file = stack.enter_context(tempfile.TemporaryFile())
            file.write(payload)
            file.flush()
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))
            for tokens, n in ((5, 2), (148, 9)):
                jobs = [
                    dict(
                        call=tokens,
                        index=i,
                        tile=i // 4 + 1,
                        layer=0,
                        wave=0,
                        tier="CPU",
                        ordinal=i,
                        expert=4,
                        slot=i,
                        generation=i + 1,
                        source_enqueue=0,
                        components=components,
                        pack_offset=0,
                    )
                    for i in range(n)
                ]
                for layout, count in (("R", 3), ("P", 1)):
                    for verify in (False, True):
                        row, raw = measure(
                            pool,
                            file.fileno(),
                            buffers,
                            layout,
                            tokens,
                            jobs,
                            lambda: None,
                            verify=verify,
                        )
                        self.assertEqual(
                            (row["requested_bytes"], row["logical_bytes"]), (24 * n, 24 * n)
                        )
                        self.assertEqual([j["index"] for j in raw["jobs"]], list(range(n)))
                        self.assertEqual(row["call_tokens"], tokens)
                        for j in raw["jobs"]:
                            self.assertEqual(len(j["read_spans_ns"]), count)
                            self.assertEqual("component_sha256" in j, verify)
                        self.assertEqual(
                            sum(row["qd_wall_ns"].values()), row["dispatch_to_drain_ns"]
                        )
            components[2]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "payload"):
                measure(pool, file.fileno(), buffers, "P", 148, jobs, lambda: None, verify=True)
            file.truncate(1)
            with self.assertRaisesRegex(OSError, "short/failed pread"):
                measure(pool, file.fileno(), buffers, "P", 148, jobs, lambda: None, verify=False)


if __name__ == "__main__":
    unittest.main()
