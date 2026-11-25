import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))


class Pages(unittest.TestCase):
    def test_adjacent_experts_chunk_multiplicity_and_reuse(self):
        # Distinct starts across file roles, unaligned like the original header.
        f = S["footprint"]([32, 1 << 30], [0, 0, 1])
        self.assertEqual(f.payload_bytes, 4 * 4406400)
        self.assertEqual(f.chunks, 10)
        self.assertGreater(f.chunk_page_bytes, S["length"](f.spans))
        pair = S["aggregate"]([f, f])
        self.assertEqual(pair.spans, f.spans)
        self.assertEqual(pair.site_page_bytes, 2 * f.site_page_bytes)
        with self.assertRaisesRegex(ValueError, "invalid expert"):
            S["footprint"]([32], [128])

    def test_pruned_output_and_true_32_threshold(self):
        # Call 2 has 32 rows upstream but only its final token enters layer 35.
        geometry = [[(5, 0, 4)], [(32, 5, 36)]]
        ranks = {
            (call, 1, layer, row): (0, 1, 2, 3)
            for call, width in ((1, 5), (2, 32))
            for layer in range(36)
            for row in range(width if layer < 35 else int(call == 2))
        }
        tiers = {layer: "CPU" if layer < 25 else "CUDA0" for layer in range(36)}
        bases = [[i * (1 << 31) + k * (1 << 29) for k in (0, 1, 2)] for i in range(36)]
        tiles, sites = S["sizes_by_tile"](ranks, geometry, tiers, bases)
        self.assertEqual([s[4:8] for s in sites if s[2] == 35], [(0, 0, 0, 0), (1, 4, 4, 0)])
        self.assertEqual(tiles[1][0]["eligible_layers"], 35)
        self.assertGreater(
            tiles[1][1]["eligible_full"]["all"].payload_bytes,
            tiles[1][1]["selective"]["all"].payload_bytes,
        )
