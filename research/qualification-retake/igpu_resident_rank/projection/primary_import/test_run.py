"""Check that the original GGML slot, page, descriptor, lease and cap are reconciled."""

import unittest
from pathlib import Path
from runpy import run_path

mod = run_path(Path(__file__).with_name("run.py"))


def journal():
    rows = []

    def add(*fields):
        rows.append("\t".join(map(str, fields)))

    s, t = mod["S"], mod["T"]
    add("scope_peak_bytes", 65536)
    add("providers", "RADV+loader+renderD128")
    add("device", "Radeon", "radv", "0000:c5:00.0", 4098, 5390, 1, 4096)
    add("variant", "subgroup", 1, 1, 64, 12, 2880)
    for k in range(3):
        add("ggml_tensor", k, k * t, t, 3 * t, 64, (64 + k * t) % 4096)
    for expert, slot, offset in ((28, 3, 371245056), (24, 14, 318210048)):
        for k in range(3):
            add("ggml_set", expert, slot, k, offset + k * s, s)
    add("scope_peak_bytes", 102400)
    for expert, slot, role in mod["STAGES"]:
        w = slot * s + role * t
        d = (64 + w) % 4096
        n = s + d
        align = ((n + 15) // 16) * 16
        allocation = ((align + 4095) // 4096) * 4096
        add("primary_range", expert, slot, role, w - d, d, n, align, allocation, 16, 5, 32, 1965)
        add("released", expert, slot, role, 0, 11520)
    add("providers", "RADV+loader+renderD128")
    add("scope_peak_bytes", 105000)
    add("PASS_PRIMARY_CPU_IMPORT")
    return "\n".join(rows)


class TestPrimary(unittest.TestCase):
    def test_dense_owner(self):
        p = mod["journal"](journal())
        self.assertEqual((p["imports"], p["primary_bytes_set"]), (3, 26438400))

    def test_corrupt_receipts(self):
        for old, new in (
            ("released\t28\t3", "released\t28\t4"),
            ("primary_range\t24\t14", "primary_range\t24\t3"),
            ("\t16\t5\t32\t1965", "\t16\t5\t1\t1965"),
            ("\t318210048", "\t371245056"),
            ("scope_peak_bytes\t105000", "scope_peak_bytes\t150000000"),
        ):
            with self.subTest(old=old), self.assertRaises(ValueError):
                mod["journal"](journal().replace(old, new))


if __name__ == "__main__":
    unittest.main()
