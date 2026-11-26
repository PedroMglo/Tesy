import unittest
from pathlib import Path
from runpy import run_path

s = run_path(str(Path(__file__).with_name("screen.py")))
fd, PAY, offers = s["fd"], s["PAY"], s["offers"]


def event(kind, component=-1, a=0, b=0, c=0, generation=4):
    return fd.Row(
        1, 1, generation, a, b, c, fd.NAMES.index(kind), 1, 1, 0, 25, 0, 0, 0, component, 3, 0, 0
    )


def rows():
    size = PAY // 3
    full = (size + 4095) // 4096 * 4096
    table = [event("WEIGHT", i, 0, size) for i in range(3)]
    for i in range(3):
        table += [event("READ", i, 0, full, size), event("SET", i, size, 0)]
    return [*table, event("PUBLISH")]


class TestPublication(unittest.TestCase):
    def test_complete_only(self):
        full = rows()
        feed, stats = offers(full)
        self.assertEqual(feed, [((25, 0), 1)])
        self.assertEqual(stats["cuda"]["observed_fd_returned_bytes"], PAY)
        with self.assertRaisesRegex(ValueError, "three staging"):
            offers(full[:-2] + full[-1:])
        with self.assertRaisesRegex(ValueError, "pending"):
            offers(full[:-1])
        with self.assertRaisesRegex(ValueError, "three staging"):
            offers(full[:-1] + [event("PUBLISH", generation=5)])
        with self.assertRaisesRegex(ValueError, "failed worker"):
            offers(full[:-1] + [event("LOAD_FAIL")])

    def test_short_payload_and_wrong_destination(self):
        complete = rows()
        for i, field, value, label in (
            (3, "c", PAY // 3 - 1, "read return"),
            (4, "b", 10, "staging order"),
        ):
            records = list(complete)
            records[i] = records[i]._replace(**{field: value})
            with self.assertRaisesRegex(ValueError, label):
                offers(records)

    def test_published_order_drives_last_distinct_keys(self):
        x, y, z = (25, 8), (31, 9), (2, 4)
        feed = [(k, 1) for k in (x, y, x, z)]
        keys, installs, _, _ = s["control"]["maintain"](feed, 2)
        self.assertEqual(keys, [x, z])
        self.assertEqual(installs, [0, 1, 3])


if __name__ == "__main__":
    unittest.main()
