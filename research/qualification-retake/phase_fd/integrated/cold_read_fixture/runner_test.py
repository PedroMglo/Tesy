import errno
import hashlib
import importlib.util
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "first_demand_runner", Path(__file__).with_name("runner.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FirstReads(unittest.TestCase):
    def test_budget_and_decisions(self):
        self.assertEqual(m.memory(4, 4415488)[1], 256 * m.MIB)
        self.assertGreater(m.memory(20, 4415488)[1], 256 * m.MIB)
        with self.assertRaises(ValueError):
            m.memory(128, 4415488)
        t = m.BUDGET_NS
        arm = dict(drain_ns=t + 5, floor_ns=t + 1)
        self.assertEqual(m.classify(arm, arm), "NO_GO_OBSERVED_FIXED_READ_PRICES")
        self.assertEqual(m.classify(arm, arm | {"floor_ns": t}), "INCONCLUSIVE_DISPATCH")
        self.assertEqual(m.classify(arm, dict(floor_ns=t - 1, drain_ns=t)), "HEADROOM_ONLY")

    def test_direct_full_short_and_hash_after_barrier(self):
        with tempfile.TemporaryDirectory() as d, ExitStack() as stack:
            file = Path(d) / "pattern.bin"
            data = b"".join(bytes([40 + i]) * 4096 for i in range(8))
            file.write_bytes(data)
            try:
                fd = os.open(file, os.O_RDONLY | os.O_DIRECT)
            except OSError as e:
                if e.errno in (errno.EINVAL, errno.EOPNOTSUPP):
                    self.skipTest("test filesystem has no O_DIRECT")
                raise
            stack.callback(os.close, fd)
            m.check_fd(fd, file, m.io.stat_id(file))
            arena = m.buffers(stack, 2, 4096)
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=4))

            def job(first, expert):
                return dict(
                    expert=expert,
                    components=[2, 0, 1],
                    ranges=[
                        [(first + i) * 4096 + 3, 100, (first + i) * 4096, 4096] for i in range(3)
                    ],
                )

            group = dict(site=[1, 1, 0, 0], experts=[job(0, 0), job(3, 1)])
            row, hashes = m.wave(pool, fd, group, arena, None)
            expected = [hashlib.sha256(bytes([40 + i]) * 100).hexdigest() for i in range(6)]
            self.assertEqual(hashes, expected)
            self.assertEqual(row["order_indices"], [0, 1])
            self.assertEqual(m.wave(pool, fd, group, arena, expected)[1], hashes)
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                m.wave(pool, fd, group, arena, list(reversed(expected)))
            with self.assertRaisesRegex(OSError, "short/failed pread"):
                m.wave(pool, fd, dict(group, experts=[job(7, 2)]), arena, None)


if __name__ == "__main__":
    unittest.main()
