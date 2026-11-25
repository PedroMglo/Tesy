import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load():
    src = Path(__file__).with_name("controller.py")
    spec = importlib.util.spec_from_file_location("t1_controller_tested", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load()


def data(delta):
    return "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n"


class Evidence:
    def __init__(self):
        self.rows = []

    def write(self, kind, **fields):
        self.rows.append((kind, fields))


class Arm(unittest.TestCase):
    def test_first_nonwhite_original_evidence_preserved_and_restored(self):
        with tempfile.TemporaryDirectory() as temp:
            armed = m.FirstText(Path(temp) / "arm")
            ev = Evidence()
            fragments = [
                ":",
                "data: [DONE]",
                data({"role": "assistant", "content": None}),
                data({"reasoning_content": "  "}),
                data({"reasoning_content": " hello"}),
                data({"content": "world"}),
            ]
            with armed.observing(ev):
                for i, line in enumerate(fragments):
                    ev.write("SSE_FRAGMENT", fragment=line)
                    self.assertEqual(armed.path.is_file(), i >= 4)
            self.assertEqual([r[1]["fragment"] for r in ev.rows], fragments)
            self.assertNotIn("write", vars(ev))
            self.assertEqual(armed.armed["fragment"], 5)
            self.assertLessEqual(armed.armed["before_ns"], armed.armed["after_ns"])

    def test_preexisting_trigger_fails_without_removing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trigger"
            path.write_bytes(b"prior")
            armed = m.FirstText(path)
            with self.assertRaises(FileExistsError), armed.observing(Evidence()) as _:
                armed.saw("SSE_FRAGMENT", {"fragment": data({"content": "x"})})
            self.assertEqual(path.read_bytes(), b"prior")

    def test_t1_prefix_sealed_before_t2_and_mutants(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "journal"
            h = m.pfj.HEADER.pack(b"TESYPF1\0", 1, m.pfj.RECORD.size, 262144, 0, 0, 0, 0)

            def row(kind, a=1):
                r = m.pfj.Row(*([0] * len(m.pfj.Row._fields)))._replace(ns=1, kind=kind, a=a)
                return m.pfj.RECORD.pack(*r)

            first, end, zero = row(1), row(2), bytes(m.pfj.RECORD.size)
            p.write_bytes(h + first + end + zero)
            seal = m.prefix_seal(p)
            self.assertEqual(seal["sha256"], hashlib.sha256(first + end).hexdigest())
            self.assertEqual(seal["records"], 2)
            p.write_bytes(h + first + end + row(1, 5))
            m.sealed_prefix(p, seal)
            p.write_bytes(h + first + row(2, a=3) + row(1, 5))
            with self.assertRaisesRegex(ValueError, "changed"):
                m.sealed_prefix(p, seal)
            for short in (first, first + row(15), row(1, 5) + end):
                p.write_bytes(h + short + zero)
                with self.assertRaises(ValueError):
                    m.prefix_seal(p)

    def test_final_and_malformed_call(self):
        self.assertTrue(m.text_event(data({"content": "ok"})))
        self.assertFalse(m.text_event('data: {"choices":[]}'))
        with self.assertRaises(ValueError):
            m.text_event(data({"content": 9}))


if __name__ == "__main__":
    unittest.main()
