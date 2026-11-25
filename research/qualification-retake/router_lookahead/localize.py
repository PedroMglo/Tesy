"""Localize the failing same-layer gate and seal the 39 private parameters for reuse."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

import numpy as np

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "score.py"))
BASE = "543316d27720db89ce660dd9cad4c0aa4f5ecadebf77f03685e1ed78bcff5fc0"
sha, need = S["sha"], S["need"]


def inspect(args, out):
    original = json.loads(S["file"](args.baseline / "receipt.json", BASE))
    rows, ident, index_sha = S["capture"](args.part23)
    params, p = S["weights"](args, ident)
    need(index_sha == original["index_sha256"] and original["weights"] == p, "same input")
    need(S["calibration"](rows, params) == original["calibration"], "same full +0")
    details, private = [], []
    for (phase, layer), s in rows.items():
        _, w, b = params[layer]
        pre, scores = S["project"](s["attn_post_norm"], w, b)
        gold = s["ffn_moe_topk"]
        ag = S["ranks"](s["ffn_moe_logits"] + b)
        observed = S["ranks"](scores)
        need(np.all(gold == ag), "native top-four")
        for j in np.where((observed != gold).any(axis=1))[0]:
            native, predicted = gold[j], observed[j]
            ordered = np.argsort(-(s["ffn_moe_logits"][j] + b), kind="stable")
            pos = int(s["start"] + j)
            details.append(
                dict(
                    phase=phase,
                    layer=layer,
                    position=pos,
                    columns=len(gold),
                    top4_set_hits=len(set(map(int, native)) & set(map(int, predicted))),
                    changed_rank_positions_1based=[
                        k + 1
                        for k, (a, b_) in enumerate(zip(native, predicted, strict=True))
                        if a != b_
                    ],
                    projected_native_ranks_1based=[
                        int(np.flatnonzero(ordered == v)[0]) + 1 for v in predicted
                    ],
                    max_abs_prebias=float(abs(pre[j] - s["ffn_moe_logits"][j]).max()),
                )
            )
            private.append(
                dict(
                    layer=layer, position=pos, truth=native.tolist(), projection=predicted.tolist()
                )
            )
    need(len(details) == 1, "mismatch count")
    sides = out / "parameters"
    sides.mkdir()
    seal = {}
    for layer, parts in enumerate(params):
        if 2 <= layer <= 24:
            continue
        for name, v in zip(S["ROLES"], parts, strict=True):
            f = f"blk.{layer}.{name}.f32"
            blob = v.tobytes(order="C")
            (sides / f).write_bytes(blob)
            need((sides / f).read_bytes() == blob, "parameter readback")
            seal[f] = dict(bytes=len(blob), sha256=sha(blob))
    need(len(seal) == 39 and sum(x["bytes"] for x in seal.values()) == 19_325_696, "private bundle")
    (out / "parameters.json").write_text(json.dumps(seal, sort_keys=True, indent=2) + "\n")
    (out / "mismatch-private.json").write_text(json.dumps(private, sort_keys=True) + "\n")
    return dict(
        status="LOCALIZED_SAME_LAYER_CONTROL",
        baseline_sha256=BASE,
        rows=details,
        weights_sha256=p["weights_sha256"],
        private_parameters_sha256=sha((out / "parameters.json").read_bytes()),
        private_mismatch_sha256=sha((out / "mismatch-private.json").read_bytes()),
        model_forwards=0,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("part23", "c7", "placement", "baseline", "new-output-dir"):
        cli.add_argument("--" + name, type=Path, required=True)
    args = cli.parse_args()
    os.umask(0o077)
    out = args.new_output_dir
    out.mkdir()
    try:
        r = inspect(args, out)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    (out / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"])
    raise SystemExit(int(r["status"] == "FAIL_PRESERVED"))
