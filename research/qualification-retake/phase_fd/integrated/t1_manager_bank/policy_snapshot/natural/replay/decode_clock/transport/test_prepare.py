import unittest
from pathlib import Path
from runpy import run_path

p = run_path(Path(__file__).with_name("prepare.py"))


class Plan(unittest.TestCase):
    def test_nonascending_rank_order_is_retained(self):
        a, b = (76, 1, 0, -1), (76, 1, 1, -1)
        refs = [{"site": s, "ranks": [4, 90, 2, 18]} for s in (a, b)]
        good = {a: {90: (1, 2), 2: (2, 3)}, b: {}}
        p["attest_order"](refs, good)
        for alt in ({a: {2: (2, 3), 90: (1, 2)}, b: {}}, {a: good[a]}, {b: {}, a: good[a]}):
            with self.assertRaises(ValueError):
                p["attest_order"](refs, alt)
        self.assertNotEqual(p["digest"]([[90, 2], []]), p["digest"]([[2, 90], []]))

    def test_components_preserve_aligned_and_payload_offsets(self):
        n = 4406400
        expert = 2
        bases = [(i * 50_000_000 + 27, n) for i in range(3)]
        components = [
            dict(
                name=f"blk.0.ffn_{role}_exps.weight",
                sha256="0f" * 32,
                type="mxfp4",
                source_offset=o + expert * n,
                packed_relative_offset=i * n,
                size_bytes=n,
            )
            for i, (role, (o, _)) in enumerate(zip(p["ROLES"], bases, strict=True))
        ]
        record = dict(layer=0, expert=expert, components=components)
        v = p["components"](record, bases)
        for i, g in enumerate(v):
            self.assertEqual(g["role"], p["ROLES"][i])
            self.assertTrue(
                g["aligned_offset"]
                <= g["source_offset"]
                < g["source_offset"] + n
                <= g["aligned_offset"] + g["aligned_bytes"]
            )
            self.assertEqual(g["aligned_offset"] % 4096, 0)
            self.assertEqual(g["aligned_bytes"] % 4096, 0)
        components[1]["source_offset"] += n
        with self.assertRaises(ValueError):
            p["components"](record, bases)

    def test_counts_clocks_and_empty_groups(self):
        rows = []
        for i in range(46 * 36):
            step, layer = divmod(i, 36)
            rows.append(
                dict(
                    step=step,
                    position=2197 + step,
                    call=76 + step,
                    tile=1,
                    layer=layer,
                    wave=-1,
                    tier="CPU" if layer < 25 else "CUDA0",
                    jobs=[],
                )
            )

        def job(e, s, source, r, t):
            return dict(
                ordinal=s,
                expert=e,
                slot=s,
                generation=1,
                source=source,
                pack_offset=e * 13258752,
                pack_bytes=13221888,
                components=[dict(aligned_bytes=4407296)] * 3,
                r0_same_site_slot=0 if r is not None else None,
                r0_same_site_generation=1 if r is not None else None,
                r0_same_site_read_ns=r,
                r0_same_site_set_ns=t,
            )

        rows[0]["jobs"] = [job(9, 0, "disk", 10, 5), job(2, 1, "bank", None, None)]

        def counts(total, known, bank, disk):
            return dict(
                admissions=total,
                common_jobs=known,
                new_jobs=total - known,
                host_bank_jobs=bank,
                disk_jobs=disk,
                disk_pack_requested_bytes=disk * 13221888,
                disk_gguf_requested_bytes=disk * 3 * 4407296,
            )

        reference = {
            name: {"inside_lower_ns": value}
            for name, value in (
                ("unidentified_pack_same_tier", 5),
                ("gguf_0p8_same_tier", 13),
                ("gguf_1_same_tier", 15),
            )
        }
        reference["gguf_1_same_tier"]["by_tier"] = {
            "cpu": counts(2, 1, 1, 1),
            "cuda": counts(0, 0, 0, 0),
        }
        proof = p["certify"](rows, reference)
        self.assertEqual(proof["tiers"]["CPU"]["empty_disk_groups"], 46 * 25 - 1)
        self.assertEqual(proof["tiers"]["CUDA0"]["empty_admission_groups"], 46 * 11)
        rows[0]["jobs"][0]["r0_same_site_set_ns"] = 4
        with self.assertRaises(ValueError):
            p["certify"](rows, reference)


if __name__ == "__main__":
    unittest.main()
