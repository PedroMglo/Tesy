import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE / "grade.py"))
B = run_path(str(HERE / "build.py"))
ROLES, SLAB, BIAS = [G[k] for k in ("ROLES", "SLAB", "BIAS")]


def small_trajectory():
    lines = []
    mats, biases, tensors = {}, {}, {}
    bank0, host0, cuda0 = 10**12, 10**13, 10**14
    for j, role in enumerate(ROLES):
        w = f"blk.0.ffn_{role}_exps.weight"
        b = f"blk.0.ffn_{role}_exps.bias"
        off = 1_000_000 + j * SLAB * 129
        tensors[w] = (off, SLAB * 128, 39)
        tensors[b] = (off + SLAB * 128, BIAS * 128, 0)
        mats[w] = (0, role)
        biases[b] = {
            1: (tensors[b][0], host0 + tensors[b][0], "CPU"),
            0: (-1, cuda0 + tensors[b][0], "CUDA0"),
        }
    for phase, width in ((3, 16), (4, 1)):

        def view(kind, name, phase=phase, width=width):
            span = 16 * width
            return f"RANK_VIEW {phase} {kind} {name} 26 4 {width} 1 1 4 16 {span} {span} {span}"

        ids = ",".join(["0,1,2,3"] * width)
        lines += [view("logical", "ffn_moe_topk-0"), f"ROUTE {phase} ffn_moe_topk-0 {ids}"]
        for j, role in enumerate(ROLES):
            w = f"blk.0.ffn_{role}_exps.weight"
            b = f"blk.0.ffn_{role}_exps.bias"
            addr = bank0 + j * SLAB * 162
            off = tensors[w][0]
            if phase == 3:
                lines += [
                    f"SET 3 {j} 0 async moe_cache.{w} {addr} 0 {SLAB * 4} {host0 + off} {off}"
                ]
                for part in range(2):
                    d = part * 2 * SLAB
                    lines += [
                        f"COPY 3 {j} async 1 {addr + d} {host0 + off + d} {SLAB * 2} {off + d} 0"
                    ]
            n = f"ffn_moe_{role}-0"
            lines += [
                f"SUBMIT {phase} {2 * j} CUDA0 0",
                view("physical", n),
                f"NODE {phase} {2 * j} mm {n} moe_cache.{w} {addr} 161 {SLAB} CUDA0 CUDA0 {ids}",
            ]
            n = f"ffn_moe_{role}_biased-0"
            device = "CPU" if phase == 4 else "CUDA0"
            bptr = biases[b][phase == 4][1]
            host = biases[b][1][1]
            lines += [
                f"SUBMIT {phase} {2 * j + 1} {device} 0",
                view("bias", n),
                f"BIAS_READ {phase} {n} {b} {bptr} {host} {tensors[b][0]} 4 {4 * BIAS}",
                f"NODE {phase} {2 * j + 1} bias {n} {b} {bptr} 1 {128 * BIAS} "
                f"{device} {device} {ids}",
            ]
    return lines, tensors, biases, mats


class WitnessTest(unittest.TestCase):
    def test_mapped_and_resident_operands_and_negative_controls(self):
        original, *args = small_trajectory()
        rows, origins, _, traffic = G["trajectory"](original, *args, 161)
        self.assertEqual([len(r["fills"]) for r in rows], [4, 0])
        self.assertEqual(origins, {"mapped_host_instance": 3, "resident_cuda_instance": 3})
        self.assertEqual(traffic["3:1"], 12 * SLAB)
        for mutation in ("remove", "late", "wrong executor", "wrong rank", "wrong bytes"):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                text = original.copy()
                i = next(i for i, r in enumerate(text) if r.startswith("COPY 3 "))
                s = next(i for i, r in enumerate(text) if r.startswith("SUBMIT 3 "))
                if mutation == "remove":
                    text.pop(i)
                elif mutation == "late":
                    text.insert(s, text.pop(i))
                elif mutation == "wrong executor":
                    text[s] = text[s].replace("CUDA0", "CPU")
                elif mutation == "wrong bytes":
                    k = next(i for i, r in enumerate(text) if r.startswith("BIAS_READ 4 "))
                    text[k] = text[k].rsplit(" ", 1)[0] + " 0"
                else:
                    k = next(
                        i for i, r in enumerate(text) if r.startswith("NODE 4 ") and " bias " in r
                    )
                    text[k] = text[k][:-1] + "9"
                G["trajectory"](text, *args, 161)

    def test_staged_bias_last_writer(self):
        orig = G["origin_for_bias"]
        base, host = 2 * 10**8, 10**7
        events = [
            (base + BIAS, BIAS // 2, host + BIAS),
            (base + BIAS + BIAS // 2, BIAS // 2, host + BIAS + BIAS // 2),
        ]
        self.assertEqual(orig(base, {1}, host, 1, events), "staged_from_mapped_duplicate")
        for bad in (events[:1], events + [(base + BIAS + 10, 1, None)]):
            with self.assertRaises(ValueError):
                orig(base, {1}, host, 1, bad)

    def test_assembled_cuts(self):
        cap, tiny = B["CAP"], B["CLI"]
        prefix = run_path(str(cap / "build.py"))["prefix"]()
        raw = B["render"](
            (cap / "capacity.cpp").read_text(),
            (tiny / "client.cpp").read_text(),
            (tiny / "rank_view.hpp").read_text(),
            prefix,
        )
        c = raw["parity.cpp"]
        self.assertLess(c.index("bias_instances(ctx);"), c.index("supplied_cuts(ctx,dir,ids);"))
        self.assertLess(c.index("supplied_cuts(ctx,dir,ids);"), c.index("llama_free(ctx);"))
        self.assertNotIn("UNEXPECTED_GRAPH_SUBMISSION", c)
        self.assertIn("if (!mm) compare_bias(t, w, arg);", c)
        self.assertIn("rank_width(node->name)", c)
        with self.assertRaises(ValueError):
            B["render"](
                (cap / "capacity.cpp").read_text().replace("p.cb_eval=nullptr;", ""),
                (tiny / "client.cpp").read_text(),
                (tiny / "rank_view.hpp").read_text(),
                prefix,
            )


if __name__ == "__main__":
    unittest.main()
