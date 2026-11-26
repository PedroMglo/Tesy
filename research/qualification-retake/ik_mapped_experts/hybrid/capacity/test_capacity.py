"""Synthetic controls for the capacity census; no model, driver, ELF or GPU is opened."""

import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(str(HERE / "grade.py"))
B = run_path(str(HERE / "build.py"))
INPUT = G["INPUT"]


class CapacityTest(unittest.TestCase):
    def test_observer_prefix_and_tiny_admission(self):
        text = B["prefix"]()
        self.assertIn("ggml_backend_tensor_set_async", text)
        self.assertIn("static void handoff(", text)
        self.assertNotIn("llama_decode(", text)
        self.assertNotIn("static int callback(", text)
        sel = B["select_tiny"]
        f = dict(
            status="PASS_TINY_HYBRID_GPU_FIXTURE",
            client_sha256="a",
            dso_sha256="b",
            model_sha256=B["T"]["GOLD"],
        )
        r = dict(status="REPRODUCED_TINY_HYBRID_GPU_FIXTURE", family_sha256="c", launches=3)
        sel(f, r, "a", "b", "c")
        for fam, rev in (
            (dict(f, status="FAIL_PRESERVED"), r),
            (f, dict(r, launches=2)),
            (f, dict(r, family_sha256="other")),
            (dict(f, client_sha256="other"), r),
        ):
            with self.assertRaises((RuntimeError, ValueError)):
                sel(fam, rev, "a", "b", "c")

    def test_copy_identity_and_incomplete_evidence(self):
        tensors = {"x.weight": (100, 8, 0), "blk.0.ffn_gate_exps.weight": (200, 16, 39)}
        a = "SET 1 1 0 sync x.weight 4000 0 8 5100 100"
        b = "COPY 1 1 async 1 4000 5100 8 100 0"
        self.assertEqual(G["controlled_transfers"]([a, b], tensors)[1]["x.weight"], [(0, 8, 4000)])
        for bad in (
            "COPY 1 1 async 1 4000 5100 8 200 0",
            "COPY 1 2 async 1 4000 5100 8 100 0",
            "COPY 1 1 async 1 4000 5100 9 100 0",
            "COPY 1 1 async 1 4001 5100 8 100 0",
            "COPY 1 1 async 1 4000 5100 8 -1 0",
            "REG 1 0 8 0 0 0",
            "PEER 1 linear 0 1 16 0",
        ):
            with self.assertRaises(ValueError):
                G["controlled_transfers"]([a, bad], tensors)

    def test_all_687_and_failures(self):
        # The table has all named logical roles and cardinalities but all payloads are four
        # bytes. This exercises placement and attribution independently of real model shapes.
        names = [
            f"blk.{layer}.ffn_{role}_exps.{kind}"
            for layer in range(36)
            for role in ("gate", "down", "up")
            for kind in ("weight", "bias")
        ]
        names += ["token_embd.weight", "output.weight", "output_norm.weight"]
        names += [f"aux_{i}.weight" for i in range(687 - len(names))]
        plan = [" ".join(["MODEL", str(INPUT["ORIGINAL"]), *map(str, INPUT["STAT"])])]
        lines = [f"MAP 0 {INPUT['STAT'][2]} 1 1", "CONTEXT 8192 1 256 32 0 0", "KV_CELLS 8192"]
        for i, name in enumerate(names, 1):
            offset, addr, source = i * 32, i * 64 + 100000, i * 32 + 1000000
            matrix = name.endswith("_exps.weight")
            host = matrix or name == "token_embd.weight"
            typ = 39 if matrix else 0
            plan.append(f"T {name} {offset} 4 {typ} 1 1 1 1")
            lines.append(
                f"PLACE {name} {typ} 4 {int(host)} {offset if host else -1} {addr} "
                f"{'CPU' if host else 'CUDA0'}"
            )
            if not host:
                lines += [
                    f"SET 1 {i} 0 sync {name} {addr} 0 4 {source} {offset}",
                    f"COPY 1 {i} sync 1 {addr} {source} 4 {offset} 0",
                ]
        lines += [
            "MEMORY CUDA0\t1\t3\t3820348800\t1\t0\t4000000000\t3",
            "MEMORY Host\t0\t7\t8\t9\t0\t0\t0",
            "STATUS COMPLETED_IK_CAPACITY_ZERO_FORWARD",
        ]
        msg = "36 layer(s), 288 expert slots\nactive MoE cache policy: classlru"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for cut in ("load.maps", "context.maps", "freed.maps"):
                (d / cut).touch()
            t = d / "plan.tsv"
            t.write_text("\n".join(plan))
            log = "\n".join(lines)
            check = G["check_arm"]
            result = check(log, msg, d, t)
            self.assertEqual(
                (
                    result["matrix_mmap_count"],
                    result["bias_cuda_count"],
                    result["expert_H2D_request_bytes"],
                ),
                (108, 108, 0),
            )
            for stdout, stderr in (
                (log, msg.replace("288", "287")),
                (log, msg + " CPU-share bank rows"),
                (log.replace("COPY 1 2 sync", "MISSING 1 2 sync"), msg),
                (log.replace("KV_CELLS 8192", "KV_CELLS 1"), msg),
                (log.replace("CONTEXT 8192 1 256 32 0 0", "CONTEXT 8192 1 256 32 0 1"), msg),
                (log.replace(" 1 1\nCONTEXT", " 1 32769\nCONTEXT"), msg),
            ):
                with self.assertRaises(ValueError):
                    check(stdout, stderr, d, t)


if __name__ == "__main__":
    unittest.main()
