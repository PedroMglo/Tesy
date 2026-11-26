import subprocess
import tempfile
import unittest
from pathlib import Path

from screen import (
    Q,
    build,
    canonical_digest,
    entropy_bounds,
    group,
    marginal,
    native_count,
    record_components,
    sha,
)


def independent_counts(blocks):
    """Explicit published byte layout for fixture only, via hexadecimal digits."""
    table = {}
    scales = [0] * 256
    nibbles = [0] * 16
    for block in blocks:
        scale, qs = block[0], block[1:]
        scales[scale] += 1
        bins = table.setdefault(scale, [0] * 16)
        for ch in qs.hex():
            n = int(ch, 16)
            bins[n] += 1
            nibbles[n] += 1
    return [[key, row] for key, row in sorted(table.items())], scales, nibbles


def make_block(scale, payload):
    assert len(payload) == 16
    return bytes([scale]) + payload


class BoundsTests(unittest.TestCase):
    def test_same_marginals_can_hide_perfect_dependence(self):
        a = [make_block(0, bytes(16)), make_block(255, bytes([0x11] * 16))] * 64
        b = [make_block(0, bytes([0x01] * 16)), make_block(255, bytes([0x01] * 16))] * 64
        ar, sa, na = independent_counts(a)
        br, sb, nb = independent_counts(b)
        self.assertEqual((sa, na), (sb, nb))
        va = entropy_bounds(ar, sa, na, len(a))
        vb = entropy_bounds(br, sb, nb, len(b))
        self.assertEqual(va["marginal_emitted_bits_floor"], vb["marginal_emitted_bits_floor"])
        self.assertEqual(va["conditional_nibble_bits_floor"], 0)
        self.assertEqual(va["mutual_information_total_bits_lo"], 32 * len(a))
        self.assertEqual(vb["mutual_information_total_bits_hi"], 0)
        self.assertEqual(vb["emitted_bits_floor"], vb["marginal_emitted_bits_floor"])
        self.assertNotEqual(va["joint_counts_sha256"], vb["joint_counts_sha256"])

    def test_exactly_one_extreme_allowance_for_all_nibble_tables(self):
        # Eight contexts, each uniform over all 16 nibble symbols. H is exactly four.
        blocks = [make_block(scale, bytes.fromhex("0123456789abcdef" * 2)) for scale in range(8)]
        rows, scales, nibbles = independent_counts(blocks)
        value = entropy_bounds(rows, scales, nibbles, len(blocks))
        count = 32 * len(blocks)
        penalty = marginal.log2_bounds(256)[1] - marginal.log2_bounds(255)[0]
        expected = -(-((count * 4 - 8) * Q - count * penalty) // Q)
        self.assertEqual(value["conditional_nibble_bits_floor"], expected)
        split_states = sum(marginal.stream_bound(c, 16, sum(c))[2] for _, c in rows)
        self.assertGreater(expected, split_states)

    def test_invalid_joint(self):
        rows, scales, nibbles = independent_counts(
            [make_block(5, bytes(16)), make_block(20, bytes([0xFF] * 16))]
        )
        for bad in (
            [rows[1], rows[0]],
            [rows[0], rows[0]],
            rows[:1],
            [[5, [True] + [0] * 15], rows[1]],
            [[5, [32]], rows[1]],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                entropy_bounds(bad, scales, nibbles, 2)
        switched = [[rows[0][0], rows[1][1]], [rows[1][0], rows[1][1]]]
        with self.assertRaisesRegex(ValueError, "nibble marginal"):
            entropy_bounds(switched, scales, nibbles, 2)

    def test_inclusive_gate_and_best_mixture(self):
        def row(expert, bits):
            return {
                "expert": expert,
                "layer": 0,
                "name": "X",
                "raw_bytes": 100,
                "h0_bits_lo": bits,
                "h0_bits_hi": bits,
                "emitted_bits_floor": bits,
                "marginal_emitted_bits_floor": bits,
                "mutual_information_total_bits_hi": 0,
                "mutual_information_total_bits_lo": 0,
            }

        result = group([row(1, 640), row(2, 700)])
        self.assertTrue(result["best_matrix_gate20_percent_reachable"])
        self.assertFalse(result["gate20_percent_reachable"])
        self.assertFalse(group([row(1, 641)])["best_matrix_gate20_percent_reachable"])

    def test_layout_bytes_include_bias_and_padding(self):
        data = b"\0WEIGHT\0\0BIAS\0"
        descriptors = [
            {"packed_relative_offset": data.index(p), "size_bytes": len(p), "sha256": sha(p)}
            for p in (b"WEIGHT", b"BIAS")
        ]
        self.assertEqual(
            [bytes(v) for v in record_components(data, descriptors)], [b"WEIGHT", b"BIAS"]
        )
        for mutation in (
            data.replace(b"BIAS", b"BIAS"[::-1]),
            data[:-1] + b"x",
            b"x" + data[1:],
            data.replace(b"\0\0", b"\0x"),
        ):
            with self.assertRaises(ValueError):
                record_components(mutation, descriptors)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.program = build(Path(cls.temp.name))

    def test_chunk_boundary_and_native_vs_independent_counts(self):
        rows = [make_block(i % 256, bytes((i + j) % 256 for j in range(16))) for i in range(1025)]
        got = native_count(self.program, b"".join(rows), len(rows))
        joint, scales, nibbles = independent_counts(rows)
        self.assertEqual(got, joint)
        self.assertEqual(
            entropy_bounds(got, scales, nibbles, len(rows))["joint_counts_sha256"],
            canonical_digest(joint),
        )

    def test_truncation_overrun_and_bad_count(self):
        valid = make_block(0, bytes(16))
        for data, n in ((valid[:-1], 1), (valid + b"\x00", 1), (valid, 0), (valid, 259201)):
            p = subprocess.run([str(self.program), str(n)], input=data, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(p.stdout, b"")


if __name__ == "__main__":
    unittest.main()
