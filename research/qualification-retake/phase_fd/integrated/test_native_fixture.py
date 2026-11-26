import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("phase_fd_fixture", HERE / "native_fixture.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Manifest(unittest.TestCase):
    def test_format_and_changed_payload(self):
        d = {str(i): str(i * 3) for i in range(171)}
        compact = json.dumps(d, separators=(",", ":"), sort_keys=True)
        expected = hashlib.sha256(compact.encode()).hexdigest()
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "inputs.json"
            path.write_text(json.dumps(d, indent=2) + "\n")
            self.assertEqual(runner.read_manifest(path, expected), d)
            d["16"] = "f"
            path.write_text(json.dumps(d, indent=2))
            with self.assertRaises(ValueError):
                runner.read_manifest(path, expected)
