import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c2_gate import GateError
from c8_seal_capture import verify


class CaptureSealTests(unittest.TestCase):
    def test_valid_and_mutated_raw_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"boundary-summary.json").write_text('{"status":"SAME_PROFILE_PASS"}')
            digest=hashlib.sha256((root/"boundary-summary.json").read_bytes()).hexdigest()
            files={"payload.bin":"a"*64}
            aggregate=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            seal=root/"capture-seal.json"
            seal.write_text(json.dumps({"schema":"c8-capture-postrun-seal-v1",
                "boundary_summary_sha256":digest,"files_sha256":files,"coverage":{"numeric_states":250},
                "aggregate_sha256":aggregate,"file_count":1}))
            with patch("c8_seal_capture.inventory",return_value=(files,{"numeric_states":250},aggregate)):
                self.assertEqual(verify(root,seal)["file_count"],1)
            changed={"payload.bin":"b"*64}
            with patch("c8_seal_capture.inventory",return_value=(changed,{"numeric_states":250},aggregate)):
                with self.assertRaises(GateError):
                    verify(root,seal)
            seal.unlink()
            with self.assertRaises(FileNotFoundError):
                verify(root,seal)
