import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

RUN = run_path(str(Path(__file__).with_name("run.py")))


def raw(path, data):
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    return raw(path, json.dumps(value).encode())


def family(root):
    on = root / "ON"
    (on / "raw").mkdir(parents=True)
    journal = raw(on / "raw/events.pfj", b"private synthetic journal")
    http = [raw(on / "raw" / f, b"{}") for f in ("T2-result.json", "T2-request.jsonl")]
    receipt = {
        "status": "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY",
        "model_launches": 1,
        "pack_events": {"label": "ON", "journal_sha256": journal, "before_second_ns": 1},
        "transport": {"mode": "P"},
        "rows": [{}, {}],
        "native_ids": {"stderr_sha256": "0" * 64},
    }
    receipt_hash = save(on / "receipt.json", receipt)
    audit = {
        "status": "PASS_PACK_NATURAL_TRACE",
        "header": {"journal_sha256": journal},
        "jobs": {"counts": {}},
        "route": {"rows": 1},
    }
    arm = {
        "status": "PASS_ONE_NATURAL_ARM",
        "mode": "ON",
        "grade": {"status": "PASS_REVIEWED_TWO_NATURAL_TURNS", "receipt_sha256": receipt_hash},
        "journal_status": audit["status"],
        "receipt_sha256": receipt_hash,
        "journal_audit_sha256": save(on / "journal-audit.json", audit),
    }
    result = {
        "status": "COMPLETED_PACK_NATURAL_OBSERVATION",
        "journal_status": audit["status"],
        "identity": {"journal_auditor_sha256": RUN["digest"](RUN["HERE"].parent / "analyse.py")},
        "arms": {"ON": {"arm": arm, "sha256": save(on / "arm.json", arm)}},
        "paired": {"clock_transfer": "INCONCLUSIVE_OUTSIDE_BAND"},
    }
    return save(root / "family.json", result), http, audit


class Wrapper(unittest.TestCase):
    def test_chain_requires_every_pin(self):
        for name in (
            "family.json",
            "ON/arm.json",
            "ON/receipt.json",
            "ON/journal-audit.json",
            "ON/raw/events.pfj",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sha, _, _ = family(root)
                RUN["chain"](root, sha)
                (root / name).write_bytes((root / name).read_bytes() + b" ")
                with self.assertRaises(ValueError):
                    RUN["chain"](root, sha)

    def test_reaudit_and_external_http_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha, http, audit = family(root)
            with (
                patch.dict(
                    RUN["NATURAL"],
                    {
                        "audit_arm": lambda *_: audit,
                        "host_trace": lambda _: {},
                        "PFJ": {"read_journal": lambda _: ([], audit["header"])},
                    },
                ),
                patch.dict(RUN["RELEASE"], {"measure": lambda *_: {"status": "TEST"}}),
            ):
                result = RUN["reproduce"](root, sha, *http)
                self.assertEqual(result["clock_transfer"], "INCONCLUSIVE_OUTSIDE_BAND")
                with self.assertRaisesRegex(ValueError, "external digest"):
                    RUN["reproduce"](root, sha, http[0], "bad")
                with patch.dict(RUN["NATURAL"], {"audit_arm": lambda *_: audit | {"route": {}}}):
                    with self.assertRaisesRegex(ValueError, "recomputed full"):
                        RUN["reproduce"](root, sha)

    def test_preserve_failure_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sha, _, _ = family(base)
            (base / "ON" / "raw/events.pfj").write_bytes(b"falsified")
            out = base / "preserved"
            with patch.object(
                sys,
                "argv",
                [
                    "run.py",
                    "--family-dir",
                    str(base),
                    "--family-sha256",
                    sha,
                    "--new-output-dir",
                    str(out),
                ],
            ):
                self.assertEqual(RUN["main"](), 1)
                prior = (out / "receipt.json").read_bytes()
                self.assertEqual(json.loads(prior)["status"], "FAIL_PRESERVED")
                with self.assertRaises(FileExistsError):
                    RUN["main"]()
                self.assertEqual((out / "receipt.json").read_bytes(), prior)


if __name__ == "__main__":
    unittest.main()
