import dis
import inspect
import unittest
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

RUN = run_path(Path(__file__).with_name("run.py"))


class Acquisition(unittest.TestCase):
    def test_frozen_handshake_and_new_child_contract(self):
        old, case = RUN["prior_case"]()
        self.assertEqual(
            list(inspect.signature(case).parameters)[-3:], ["pack", "gold", "progress"]
        )
        self.assertIs(case.__globals__["owner_handoff"], old["owner_handoff"])
        self.assertIs(case.__globals__["verify_maps"], old["verify_maps"])
        constants = [i.argval for i in dis.get_instructions(case) if i.opname.startswith("LOAD_")]
        self.assertIn(60, constants)
        self.assertNotIn(30, constants)

    def test_existing_target_rejected_before_pack(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "new NVMe"):
                RUN["generated_pack"](Path(temp), Path(temp) / "raw", {})


if __name__ == "__main__":
    unittest.main()
