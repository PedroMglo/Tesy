"""Compare the compiled projector on the archived C270 and C299 cuts without opening the GGUF."""

import argparse
import ctypes as c
import json
import subprocess
import time
from pathlib import Path
from runpy import run_path

import numpy as np

HERE = Path(__file__).resolve().parent
TF = run_path(str(HERE.parents[1] / "tf32/score.py"))
P = TF["P"]


def run(a, out, r):
    old = json.loads(P.file(HERE.parents[1] / "receipt.json", TF["BASE"]))
    params = TF["parameters"](a.c7, a.bundle, old["weights"]["weights_sha256"])
    rows, _, index = P.capture(a.part23)
    P.need(index == old["index_sha256"], "archived rows")
    so = out / "projector.so"
    subprocess.run(
        [
            "/usr/bin/c++",
            "-std=gnu++17",
            "-O3",
            "-DNDEBUG",
            "-fPIC",
            "-shared",
            str(HERE / "replay.cpp"),
            "-o",
            str(so),
        ],
        check=True,
        timeout=25,
    )
    fn = c.CDLL(str(so)).run_batch
    f32 = np.ctypeslib.ndpointer(dtype="<f4", flags="C_CONTIGUOUS")
    i32 = np.ctypeslib.ndpointer(dtype="<i4", flags="C_CONTIGUOUS")
    fn.argtypes = [c.c_int, c.c_int, f32, f32, f32, f32, f32, i32]
    fn.restype = c.c_int
    ones = np.ones(2880, dtype="<f4")
    reference = TF["surrogate"](params)
    r.update(
        index_sha256=index,
        weights_sha256=old["weights"]["weights_sha256"],
        reference_rows=0,
        reference_order_mismatches=0,
        forecast={},
        widths=[],
        projector_sha256=P.sha((HERE / "projector.h").read_bytes()),
        replay_image_sha256=P.sha(so.read_bytes()),
    )
    widths = set()
    for (phase, target), item in sorted(rows.items()):
        gold = item["ffn_moe_topk"]
        n = len(gold)
        widths.add(n)
        gamma, weights, bias = params[target]
        for offset in (0, 1):
            src = rows.get((phase, target - offset))
            if src is None:
                continue
            start = item["start"] - src["start"]
            x = np.ascontiguousarray(src["attn_post_norm"][start : start + n])
            P.need(0 <= start and x.shape == (n, 2880), "same absolute positions")
            ids = np.empty((n, 4), dtype="<i4")
            g1, g2 = (params[target - 1][0], gamma) if offset else (ones, ones)
            P.need(fn(target, n, x, g1, g2, weights, bias, ids) == 0, "projector")
            if not offset:
                r["reference_rows"] += n
                r["reference_order_mismatches"] += int((ids != gold).any(axis=1).sum())
                continue
            antecedent = P.ranks(reference((x / g1) * g2, weights, bias)[1])
            key = ("prefill" if phase.startswith("prefill") else "decode") + (
                "/CPU" if target < 25 else "/CUDA"
            )
            cell = r["forecast"].setdefault(
                key, dict(rows=0, hits=0, order_mismatches_vs_surrogate=0)
            )
            cell["rows"] += n
            cell["hits"] += int((ids[:, :, None] == gold[:, None, :]).any(axis=2).sum())
            cell["order_mismatches_vs_surrogate"] += int((ids != antecedent).any(axis=1).sum())
    r["widths"] = sorted(widths)
    P.need(r["reference_rows"] == 3400, "calibration population")
    r["status"] = (
        "PASS_ARCHIVED_ROUTER_RANKS"
        if not r["reference_order_mismatches"]
        else "INCONCLUSIVE_ARCHIVED_ROUTER_RANKS"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("c7", "bundle", "part23", "new-output-dir"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700)
    begin = time.monotonic()
    r = dict(status="FAIL_PRESERVED", gguf_read_bytes=0, model_forwards=0)
    try:
        run(a, out, r)
    except Exception as e:
        r["error"] = repr(e)
    r["duration_s"] = time.monotonic() - begin
    with (out / "receipt.json").open("x") as f:
        json.dump(r, f, sort_keys=True, indent=2)
        f.write("\n")
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
