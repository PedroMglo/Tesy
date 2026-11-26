"""Exercise shape, role and lease ordering without real weights or a device."""

import struct
import unittest
from pathlib import Path
from runpy import run_path

r = run_path(Path(__file__).with_name("run.py"))


def log():
    w = r["W"]

    def tag(k, *args):
        return "\t".join([k, *map(str, args)])

    lines = [
        tag("scope_peak_bytes", 2048),
        tag("device", "Radeon", "radv", "0000:c5:00.0", 4098, 5390, 1, 4096),
        tag("type", 5, 0, 14),
        tag("providers", "RADV+loader+renderD128"),
        tag("queue", 0, 15),
        tag("variant", "subgroup", 1, 1, 64, 12, 2880),
    ]
    lines += [tag("import", 65536, 16, 32, 1965, 5, 0, 14)] * 4
    for ino, gen, e, off in ((50, 6, 28, 371245056), (51, 7, 24, 318210048)):
        lines.append(tag("window_import", gen, ino, w, w, 16, 16, 5, 32, 1965, 14))
        lines.append(tag("publish", 3, e, gen, ino, w, off, 3 * w))
        if gen == 7:
            lines.append(tag("stale_rejected", 3, 6, 7))
        lines.append(tag("acquire", 3, gen, ino))
        if gen == 6:
            lines.append(tag("blocked_replacement", 6, 7))
        for role in [0, 2] if gen == 6 else [0]:
            lines.append(tag("role_result", e, gen, role, ino, role * r["ROLE"], 0, 11520))
        lines.append(tag("release_after_fence", gen, ino))
    lines += [
        tag("providers", "RADV+loader+renderD128"),
        tag("scope_peak_bytes", 8888888),
        "PASS_RANK_BACKING_DISPATCH",
    ]
    return "\n".join(lines)


class RankBacking(unittest.TestCase):
    def test_lease(self):
        self.assertEqual(r["journal"](log())["pack_read_bytes"], 2 * r["W"])
        for a, b in (
            ("stale_rejected", "accepted"),
            ("release_after_fence", "pending"),
            ("8812800", "4406400"),
            ("318210048", "371245056"),
            ("\t7\t51", "\t7\t50"),
        ):
            with self.subTest(a=a), self.assertRaises(ValueError):
                r["journal"](log().replace(a, b))

    def test_numerics(self):
        g = {name: struct.pack("<f", i + 1) * 2880 for i, (_, _, name) in enumerate(r["CASES"])}
        self.assertEqual(r["assess"](g, g)["decision"], "GO_BACKING_AND_TWO_ROLES_ONLY")
        a = dict(g)
        a["e28-up"] = g["e28-gate"]
        self.assertEqual(r["assess"](a, g)["rows"]["e28-up"]["unequal"], 2880)
        a["e24-gate"] = g["e28-gate"]
        with self.assertRaises(ValueError):
            r["assess"](a, g)


if __name__ == "__main__":
    unittest.main()
