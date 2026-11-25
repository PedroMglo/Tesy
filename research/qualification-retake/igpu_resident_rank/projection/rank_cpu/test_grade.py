import copy
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402


def matrix(values):
    return b"".join(struct.pack("<f", value) * grade.K for value in values)


def fixture():
    values = {stage + ".f32": matrix((0, 0, 0, 0)) for stage in grade.STAGES}
    values["down-biased.f32"] = matrix((2**26, 4, -(2**28), 8))
    values["weighted.f32"] = matrix((2**25, 1, -(2**25), 1))
    values["mix.f32"] = struct.pack("<4f", 0.5, 0.25, 0.125, 0.125)
    values["down-rank0.q8"] = bytes(3060)
    final = struct.pack("<f", 1) * grade.K
    return values, final


class TestRank(unittest.TestCase):
    def test_order_controls_and_router(self):
        data, final = fixture()
        q = lambda _: bytes(3060)  # noqa: E731
        self.assertEqual(len(grade.compare_stages(data, final, q)["weighted"]), 4)
        with self.assertRaisesRegex(ValueError, "left-associated"):
            grade.compare_stages(data, bytes(grade.ROW), q)
        corrupt = dict(data, **{"weighted.f32": matrix((2**25, 1, 1, -(2**25)))})
        with self.assertRaisesRegex(ValueError, "router product"):
            grade.compare_stages(corrupt, final, q)
        corrupt = dict(data, **{"down-rank0.q8": bytes(3059) + b"\x01"})
        with self.assertRaisesRegex(ValueError, "rank zero Q8_0"):
            grade.compare_stages(corrupt, final, q)
        corrupt = dict(data, **{"up.f32": struct.pack("<f", float("nan")) + data["up.f32"][4:]})
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            grade.compare_stages(corrupt, final, q)

    def test_full_schema_and_corruption(self):
        data, final = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rank = root / "rank"
            rank.mkdir()
            (root / "native").mkdir()
            (root / "native" / "decode.f32").write_bytes(final)
            for name, blob in data.items():
                (rank / name).write_bytes(blob)
            cpu, base = root / "cpu", root / "base"
            cpu.write_bytes(b"cpu")
            base.write_bytes(b"base")
            prior = dict(
                status="PASS_C291_CPU0_DECODE_HANDOFF",
                mode="ALIAS",
                finite=True,
                unequal=0,
                mmid_nodes=3,
                add_id_nodes=3,
                equal_components=24,
                hits=3,
                misses=1,
                joined_workers=4,
                providers={"cpu": str(cpu), "base": str(base)},
            )
            proof = dict(
                status="PASS_CPU0_RANK_STAGES_CAPTURE",
                shape=[2880, 4, 1, 1],
                logical=[28, 24, 8, 16],
                physical=[3, 14, 6, 35],
                generations=[6, 6, 5, 4],
                mmid_edges=3,
                bias_edges=3,
                glu_edges=1,
                weighted_edges=1,
                reduction_views=4,
                reduction_adds=3,
                biased_values_checked=34560,
                files_sha256={name: grade.sha(v) for name, v in data.items()},
                provider_cpu=str(cpu),
                provider_base=str(base),
            )
            header = rank / "rank.json"
            header.write_text(json.dumps(proof))
            pins = dict(
                GOLD=grade.sha(final),
                GATE=grade.sha(bytes(grade.ROW)),
                MIX=grade.sha(data["mix.f32"]),
                CPU=grade.sha(b"cpu"),
                BASE=grade.sha(b"base"),
            )
            with patch.multiple(grade, **pins):
                result = grade.verify_rank(rank, prior)
                self.assertEqual(result["f32_router_products"], 11520)
                self.assertEqual(result["status"], "PASS_CPU0_RANK_STAGES_REVIEW")
                for key, value in [
                    ("logical", [24, 28, 8, 16]),
                    ("glu_edges", True),
                    ("provider_base", str(cpu)),
                ]:
                    wrong = copy.deepcopy(proof)
                    wrong[key] = value
                    header.write_text(json.dumps(wrong))
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        grade.verify_rank(rank, prior)
                header.write_text(json.dumps(proof))
                (rank / "extra.f32").write_bytes(b"")
                with self.assertRaisesRegex(ValueError, "census"):
                    grade.verify_rank(rank, prior)


if __name__ == "__main__":
    unittest.main()
