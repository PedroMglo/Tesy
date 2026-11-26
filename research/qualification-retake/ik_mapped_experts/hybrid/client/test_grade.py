"""Synthetic address/routing traces, including coalesced writes and a later reuse."""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade as g  # noqa: E402


def artificial(mode, folder):
    event = []
    log = []
    next_id = 0
    slots = {"BANK7": 7, "BANK9": 9}.get(mode, 0)

    def upload(phase, name, dest, off, amount, origin):
        nonlocal next_id
        next_id += 1
        ptr = 10000000 + origin
        event.append(f"SET {phase} {next_id} 0 async {name} {dest} {off} {amount} {ptr} {origin}")
        event.append(f"COPY {phase} {next_id} async 1 {dest + off} {ptr} {amount} {origin} 0")

    for k, ((layer, role), offset) in enumerate(g.WEIGHTS.items()):
        original = f"blk.{layer}.ffn_{role}_exps"
        base = 20000000 + k * 400000
        if mode == "RESIDENT":
            upload(1, original + ".weight", base, 0, g.TENSOR, offset)
        loc = "CUDA0" if mode == "RESIDENT" else "CPU"
        wo = -1 if mode == "RESIDENT" else offset
        bo = -1 if mode == "RESIDENT" else offset + g.TENSOR
        event.extend(
            [
                f"ORIG {original}.weight {base} {g.TENSOR} {wo} 39 {loc}",
                f"ORIG {original}.bias 123 8192 {bo} 0 {loc}",
            ]
        )
    if slots:
        log.append(f"2 layer(s), {slots} expert slots")
    if slots == 7:
        log.append("skipped 0 large-batch and 2 ineligible layer accesses")
    for phase, width in g.WIDTHS.items():
        active = slots and (slots == 9 or width == 1)
        for layer in range(2):
            tok = ",".join(map(str, [0, 1, 2, 3] * width))
            layout = f"26 4 {width} 1 1 4 16 {width * 16} {width * 16} {width * 16}"
            event.append(f"RANK_VIEW {phase} logical ffn_moe_topk-{layer} {layout}")
            event.append(f"ROUTE {phase} ffn_moe_topk-{layer} {tok}")
            start = 0 if layer == 0 else min(4, slots - 4)
            canonical = ",".join(map(str, list(range(start, start + 4)) * width)) if active else tok
            for j, role in enumerate(g.ROLES):
                name = f"blk.{layer}.ffn_{role}_exps"
                ptr = 20000000 + (3 * layer + j) * 400000
                if active:
                    ptr = 30000000 + j * 500000
                    if slots == 7 or phase == 3:
                        upload(
                            phase,
                            "moe_cache." + name + ".weight",
                            ptr,
                            start * g.SLAB,
                            g.SLAB * 4,
                            g.WEIGHTS[layer, role],
                        )
                for op in ("mm", "bias"):
                    ident = 10 * layer + 2 * j + int(op == "bias")
                    backend = "CUDA0" if mode == "RESIDENT" or active else "CPU"
                    weight = ("moe_cache." if active and op == "mm" else "") + name
                    suffix = "_biased" if op == "bias" else ""
                    kind = "physical" if op == "mm" else "bias"
                    event.append(
                        f"RANK_VIEW {phase} {kind} ffn_moe_{role}{suffix}-{layer} {layout}"
                    )
                    event.append(f"SUBMIT {phase} {ident} {backend} 0")
                    event.append(
                        f"NODE {phase} {ident} {op} ffn_moe_{role}{suffix}-{layer} "
                        f"{weight}.{'weight' if op == 'mm' else 'bias'} {ptr} "
                        f"{slots if active else 8} {g.SLAB} {backend} {backend} "
                        + (canonical if op == "mm" else tok)
                    )
        if active:
            fill = 8 if phase == 3 or slots == 7 else 0
            key = "ubatch 9-32" if phase == 3 else "ubatch <= 8"
            log.append(
                f"{key} hits={8 - fill} gpu_fills={fill} cpu_serviced_unique_misses=0 "
                f"unique_keys=8 unique_key_hit_rate=0.0% logical_uploaded_bytes={fill * 3 * g.SLAB}"
            )
    for name, width in (("prefill", 32), ("teacher", 1)):
        (folder / (name + ".f32")).write_bytes(struct.pack("<32f", *range(32)) * width)
    event.append("STATUS COMPLETED_TINY_HYBRID_CLIENT")
    return "\n".join(event), "\n".join(log)


class Evidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name)

    def test_all_branches_and_reuse(self):
        for m in g.MODES:
            text, log = artificial(m, self.d)
            row = g.check_arm(m, text, log, self.d)
            with self.subTest(mode=m):
                self.assertEqual(row["consumer_ops"], 24)
                self.assertEqual(row["startup_matrix_H2D_bytes"], 1671168 if m == "RESIDENT" else 0)
                self.assertEqual(row["reconciled"]["teacher"]["hits"], 8 if m == "BANK9" else 0)
                self.assertEqual(row["reconciled"]["teacher"]["fills"], 8 if m == "BANK7" else 0)

    def test_bad_binding_missing_role_false_hit_blind_observer(self):
        text, log = artificial("BANK9", self.d)
        lines = text.splitlines()
        for mut in (
            text.replace("moe_cache.blk.0.ffn_gate_exps.weight", "blk.0.ffn_gate_exps.weight"),
            text.replace("0,1,2,3", "0,1,2,2", 1),
            "\n".join(line for line in lines if not line.startswith("COPY 3 1 ")),
            text.replace(" 4,5,6,7", " 4,5,6,3", 1),
            text.replace(
                "NODE 4 0 mm ffn_moe_gate-0 moe_cache.blk.0.ffn_gate_exps.weight 30000000",
                "NODE 4 0 mm ffn_moe_gate-0 moe_cache.blk.0.ffn_gate_exps.weight 31000001",
            ),
            "COPY 2 0 async 1 10 12 64 -1 0\n" + text,
            text.replace(
                "STATUS COMPLETED_TINY_HYBRID_CLIENT",
                "PEER 3 linear 0 1 32 0\nSTATUS COMPLETED_TINY_HYBRID_CLIENT",
            ),
        ):
            with self.assertRaises(ValueError):
                g.check_arm("BANK9", mut, log, self.d)
        text, log = artificial("RESIDENT", self.d)
        with self.assertRaisesRegex(ValueError, "transfer extent"):
            g.check_arm(
                "RESIDENT",
                "\n".join(row for row in text.splitlines() if not row.startswith("COPY")),
                log,
                self.d,
            )

    def test_moved_transfer_and_overlap(self):
        text, log = artificial("BANK9", self.d)
        lines = text.splitlines()
        ci = next(i for i, row in enumerate(lines) if row.startswith("COPY "))
        lines.insert(-1, lines.pop(ci))
        with self.assertRaisesRegex(ValueError, "routed site|after consumer"):
            g.check_arm("BANK9", "\n".join(lines), log, self.d)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            g.coverage([(0, 2), (1, 2)], 4)

    def test_cross_arm_numeric_and_unknown_bytes(self):
        ref = self.d / "ref"
        cand = self.d / "candidate"
        ref.mkdir()
        cand.mkdir()
        rtext, rlog = artificial("RESIDENT", ref)
        ctext, clog = artificial("BANK9", cand)
        a = g.check_arm("RESIDENT", rtext, rlog, ref)
        b = g.check_arm("BANK9", ctext, clog, cand)
        match = g.compare_arms(ref, a, cand, b)
        self.assertTrue(match["bitwise"] and match["routes_equal"])
        f = cand / "teacher.f32"
        f.write_bytes(struct.pack("<f", -0.0) + f.read_bytes()[4:])
        with self.assertRaisesRegex(ValueError, "identity"):
            g.compare_arms(ref, a, cand, b)
        b = g.check_arm("BANK9", ctext, clog, cand)
        diff = g.compare_arms(ref, a, cand, b)
        self.assertFalse(diff["bitwise"])
        self.assertTrue(diff["routes_equal"])
        self.assertEqual(diff["rows"]["teacher.f32"]["different_words"], 1)
        self.assertEqual(diff["rows"]["teacher.f32"]["max_abs"], 0)
        self.assertEqual(
            g.nonmatrix_source(g.OFFSETS[1][1] + g.TENSOR, 20, None), "mapped_bias_L1_up"
        )
        self.assertEqual(g.nonmatrix_source(-1, 2, None), "unattributed_host")


if __name__ == "__main__":
    unittest.main()
