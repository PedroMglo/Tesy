import struct
import sys
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grade  # noqa: E402
import run  # noqa: E402

ARITH = run_path(HERE.parent / "reference/arithmetic.py")


def x4(q):
    image = bytearray(23 * 144)
    for b in range(90):
        base, lane = divmod(b, 4)
        pos = base * 144
        image[pos + 4 * lane : pos + 4 * lane + 2] = q[34 * b : 34 * b + 2]
        image[pos + 16 + 32 * lane : pos + 48 + 32 * lane] = q[34 * b + 2 : 34 * b + 34]
    return bytes(image)


class ActivationTests(unittest.TestCase):
    def test_partition_roundtrip_and_edges(self):
        gate = struct.pack("<2880f", *range(2880))
        up = struct.pack("<2880f", *(-i for i in range(2880)))
        packets = grade.segments(gate, up)
        self.assertEqual(len(packets), 4)
        outputs = []
        for index, packet in enumerate(packets):
            self.assertEqual(len(packet), 11520)
            self.assertEqual(packet[:2880], gate[index * 2880 : (index + 1) * 2880])
            self.assertEqual(packet[2880:5760], up[index * 2880 : (index + 1) * 2880])
            self.assertEqual(packet[5760:], bytes(5760))
            outputs.append(packet[:2880] + grade.SENTINEL * 108)
        self.assertEqual(grade.assemble(outputs), gate)
        for bad in (
            bytes(3312),
            grade.SENTINEL * 828,
            outputs[0][:-4],
            struct.pack("<f", float("nan")) + outputs[0][4:],
        ):
            with self.assertRaises(ValueError):
                grade.segment_output(bad)

    def test_activation_and_quantizer_are_separate(self):
        base = struct.pack("<32f", 1, *([0] * 31)) * 90
        near = base[:4] + struct.pack("<f", 2**-10) + base[8:]
        q_cpu = ARITH["quantize"](base)
        same = grade.evaluate(base, q_cpu, base, x4(q_cpu), ARITH)
        self.assertEqual(same["decision"], "EQUAL_F32_AND_EFFECTIVE_DOWN_OPERAND")
        e = grade.evaluate(base, q_cpu, near, x4(q_cpu), ARITH)
        self.assertEqual(e["decision"], "EQUAL_EFFECTIVE_DOWN_OPERAND_ONLY")
        self.assertEqual(e["f32"]["first"], 1)
        self.assertTrue(e["activation_at_cpu_quantizer"]["same_input"])
        wrong = bytearray(x4(q_cpu))
        wrong[17] = 1
        e = grade.evaluate(base, q_cpu, near, wrong, ARITH)
        self.assertEqual(e["decision"], "DIFFERENT_EFFECTIVE_DOWN_OPERAND")
        self.assertEqual(e["quantizer_on_gpu_activation"]["first_code"], 1)
        wrong[-1] = 1
        with self.assertRaisesRegex(ValueError, "padding"):
            grade.evaluate(base, q_cpu, near, wrong, ARITH)
        with self.assertRaisesRegex(ValueError, "CPU SwiGLU"):
            grade.evaluate(base, bytes(3060), near, wrong, ARITH)

    def test_signed_zero_and_spirv_gate(self):
        left = bytes(11520)
        right = struct.pack("<I", 0x80000000) + left[4:]
        d = grade.f32_diff(left, right)
        self.assertEqual((d["changed_bits_words"], d["changed_values"], d["max_ulp"]), (1, 0, 0))
        with self.assertRaises(ValueError):
            run.reflect(bytes(20))


if __name__ == "__main__":
    unittest.main()
