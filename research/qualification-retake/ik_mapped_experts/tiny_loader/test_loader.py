import struct
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).parent
driver = run_path(str(HERE / "run.py"))
generate = run_path(str(HERE / "data.py"))["generate"]


class SyntheticLoader(unittest.TestCase):
    def test_weight_bytes_offsets_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "s.gguf"
            layout = generate(model)
            self.assertEqual(model.stat().st_size, 3390592)
            self.assertEqual(
                driver["sha"](model),
                "3771d5de5067095852a0132324c16b01e39c2b999082d4a3b6165e13aff90644",
            )
            self.assertEqual(sum(n for _, n, typ in layout.values() if typ == 39), 1671168)
            self.assertEqual(
                driver["expected_drops"](layout), [(872448, 856064, 4, 0), (2531328, 856064, 4, 0)]
            )

    def test_defer_rejects_original_bulk_or_wrong_view(self):
        table = {
            f"blk.{layer}.ffn_{role}_exps.{kind}": [8192 + 16384 * i, 8192, typ]
            for i, (layer, role, kind, typ) in enumerate(
                (layer, role, kind, typ)
                for layer in range(2)
                for role in ("gate", "up", "down")
                for kind, typ in (("weight", 39), ("bias", 0))
            )
        }
        size = 1 << 20
        lines = [f"MAP 0 {size} 1 1", "POOL 1 1 0", "RSS 12345"]
        lines += ["MAD " + " ".join(map(str, r)) for r in driver["expected_drops"](table)]
        lines += [f"VIEW {k} {v[0]} {v[1]} {v[2]}" for k, v in table.items()]
        log = "\n".join(lines)
        raw = struct.pack("<32f", *range(32))
        self.assertEqual(driver["grade"]("DEFER", log, table, size, raw)["greedy"], 31)
        for mutation in (
            log + f"\nPOSIX 0 {size} 3 0",
            log.replace("VIEW", "BAD", 1),
            log.replace("8192 8192 4 0", "8192 4096 4 0", 1),
        ):
            with self.assertRaises(ValueError):
                driver["grade"]("DEFER", mutation, table, size, raw)
