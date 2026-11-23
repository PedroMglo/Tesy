import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from c2_gate import GateError
from c117_analyze import require_arm_inventory


class TestC117StartInventory(unittest.TestCase):
    def test_valid_and_discriminating_mutations(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "raw").mkdir()
            run_id = "test-arm"
            with self.assertRaisesRegex(GateError, "missing per-arm"):
                require_arm_inventory(root, run_id)
            path = root / "raw" / f"{run_id}.start-inventory.jsonl"

            def write(times):
                path.write_text("".join(json.dumps({"elapsed_s": t}) + "\n" for t in times))

            write(range(61))
            self.assertEqual(require_arm_inventory(root, run_id), 61)
            write(range(60))
            with self.assertRaisesRegex(GateError, "short per-arm"):
                require_arm_inventory(root, run_id)
            write([*range(30), *range(32, 63)])
            with self.assertRaisesRegex(GateError, "cadence"):
                require_arm_inventory(root, run_id)


if __name__ == "__main__":
    unittest.main()
