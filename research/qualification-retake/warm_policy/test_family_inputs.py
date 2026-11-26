"""The offline policy screen must reject incomplete or contradictory physical receipts."""

import copy
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import evaluate
from warm_route_reference import verify


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    data = value if isinstance(value, bytes) else json.dumps(value).encode()
    path.write_bytes(data)
    return sha(data)


class FamilyInputs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        raw = self.root / "raw"
        raw.mkdir()
        gold = {"P": "P", "F": "F", "gold": sha(b"logits")}
        plan = dict(
            schema="tesy-warm-route-family-v1",
            measurement_commit="commit",
            unit_stem="test",
            order=evaluate.ARM_ORDER,
            executable_sha256="client",
            independent_reference={case: gold for case in verify.PROMPT},
        )
        self.receipt = dict(
            status="PASS_WARM_ROUTE_FAMILY",
            not_run=[],
            model_launch_receipts=4,
            plan_sha256=write(self.root / "protocol.json", plan),
            measurement_commit="commit",
            arms=[],
        )
        for i, (case, mode) in enumerate(evaluate.ARM_ORDER, 1):
            unit = f"test-{i}-{case}-{mode.lower()}"
            native = raw / (unit + ".native")
            native.mkdir()
            locked = write(self.root / (unit + ".json"), dict(plan, execution_scope_unit=unit))
            inventory = write(raw / (unit + ".start-inventory.receipt.json"), {"id": unit})
            common = dict(
                run_id=unit,
                binary_sha256="client",
                process_identity={"pid": i},
                start_inventory={"receipt_sha256": inventory},
            )
            monitor = dict(
                common, returncode=0, stop_reason=None, limits={"resource_protocol_sha256": locked}
            )
            launch = dict(common, resource_protocol_sha256=locked)
            hashes = {
                k: write(native / k, v)
                for k, v in {
                    "initial.json": {},
                    "result.json": {},
                    "events.tsv": b"header",
                    "all33.logits.f32": b"logits",
                }.items()
            }
            self.receipt["arms"].append(
                dict(
                    case=case,
                    mode=mode,
                    run_id=unit,
                    native_dir=str(native.relative_to(self.root)),
                    status="PASS_WARM_ROUTE_ARM",
                    scope_returncode=0,
                    monitor_stop=None,
                    process_and_scope_closed=True,
                    monitor_sha256=write(raw / (unit + ".json"), monitor),
                    launch_sha256=write(raw / (unit + ".launch.json"), launch),
                    inventory_sha256=inventory,
                    native_sha256=hashes,
                    P_sha256="P",
                    F_sha256="F",
                )
            )

    def admit(self, receipt):
        return evaluate.family_inputs(self.root, write(self.root / "receipt.json", receipt))

    def test_complete_and_failed_metadata(self):
        self.assertEqual(len(self.admit(self.receipt)), 4)
        for target, key, bad in [
            ("family", "not_run", ["OFF"]),
            ("family", "model_launch_receipts", 3),
            ("family", "measurement_commit", "old"),
            ("family", "plan_sha256", "broken"),
            ("arm", "status", "FAIL_PRESERVED"),
            ("arm", "scope_returncode", 1),
            ("arm", "monitor_stop", "OOM"),
            ("arm", "process_and_scope_closed", False),
            ("arm", "run_id", self.receipt["arms"][1]["run_id"]),
            ("arm", "monitor_sha256", "old"),
            ("arm", "launch_sha256", "old"),
            ("arm", "inventory_sha256", "old"),
        ]:
            with self.subTest(target=target, key=key):
                row = copy.deepcopy(self.receipt)
                (row if target == "family" else row["arms"][0])[key] = bad
                with self.assertRaises(ValueError):
                    self.admit(row)

    def test_off_journal_and_changed_native(self):
        d = self.root / self.receipt["arms"][0]["native_dir"]
        (d / "prefix-routes.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "OFF emitted"):
            self.admit(self.receipt)
        (d / "prefix-routes.bin").unlink()
        (d / "all33.logits.f32").write_bytes(b"other")
        with self.assertRaisesRegex(ValueError, "changed native"):
            self.admit(self.receipt)

    def test_resealed_cross_arm_monitor(self):
        row = self.receipt["arms"][0]
        target = self.root / "raw" / (row["run_id"] + ".json")
        monitor = json.loads(target.read_bytes())
        monitor["process_identity"] = {"pid": 2}
        row["monitor_sha256"] = write(target, monitor)
        with self.assertRaisesRegex(ValueError, "inconsistent physical"):
            self.admit(self.receipt)

    def case_data(self, mutate_rank):
        case = "nominal153"
        wrt, tpr = bytearray(b"WRT1"), bytearray(b"TPR1")
        for pos in range(41):
            wrt.extend(b"C" + struct.pack("<HH", pos, 1) + b"U" + struct.pack("<BH", 1, pos))
            tpr.extend(
                b"C" + struct.pack("<HH", pos + 1, 1) + b"U" + struct.pack("<HBHB", 1, 1, pos, 1)
            )
            for layer in range(36):
                if layer == 35:
                    wrt.extend(b"O\x00")
                ids = bytes(
                    (4, 5, 6, 7) if not (mutate_rank and pos == 9 and layer == 0) else (5, 4, 6, 7)
                )
                wrt.extend(b"R" + struct.pack("<BBH", layer, 1, 16) + ids)
                tpr.extend(b"R" + bytes((layer, ord("S"), 1)) + ids)
            wrt.extend(b"ED")
            tpr.extend(b"ED")
            if pos in (7, 8):
                tpr.extend(b"P" if pos == 7 else b"I")
        wrt.extend(b"F")
        tpr.extend(b"F")
        expected = sha(bytes((4, 5, 6, 7)) * (32 * 36))
        cases = self.receipt["arms"][:2]
        for row in cases:
            d = self.root / row["native_dir"]
            hashes = row["native_sha256"]
            hashes["boundary-i.json"] = write(d / "boundary-i.json", {"id": "I"})
            hashes["routed-witness.bin"] = write(d / "routed-witness.bin", bytes(wrt))
            if row["mode"] == "ON":
                hashes["prefix-routes.bin"] = write(d / "prefix-routes.bin", bytes(tpr))
            row.update(decode_sha256=expected, groups=41 * 36, ubatches=41, I_sha256="I")
        return case, cases, expected

    def test_contemporary_rank_and_both_boundary_receipts(self):
        for mutate_rank in (False, True):
            case, rows, expected = self.case_data(mutate_rank)
            with (
                patch.dict(verify.PROMPT, {case: 9}),
                patch.dict(verify.SHA, {case: expected}),
                patch.object(evaluate, "verify_boundary", return_value={"slot_vector_sha256": "I"}),
            ):
                if mutate_rank:
                    # WRT OFF/ON and TPR agree with each other on the wrong ranks.
                    with self.assertRaisesRegex(ValueError, "ordered decode reference mismatch"):
                        evaluate.case_inputs(self.root, case, rows)
                else:
                    self.assertEqual(evaluate.case_inputs(self.root, case, rows)[1], "I")
                    for arm in rows:
                        arm["I_sha256"] = "old"
                        with self.assertRaisesRegex(ValueError, "arm I receipt"):
                            evaluate.case_inputs(self.root, case, rows)
                        arm["I_sha256"] = "I"


if __name__ == "__main__":
    unittest.main()
