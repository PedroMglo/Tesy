"""Test the specified TF32 operand surrogate on the qualified C270 router cuts."""

import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("router_f32_control", HERE.parent / "score.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
need, file, sha = P.need, P.file, P.sha
METHOD = "91caf54a367a6912b26cbf92abebe9a725a0622285a644d73eacf23e1459ac61"
BUNDLE = "48a9e35554d2805c04b484b2a51d2e057d1e0cd453f535ee44f7db8e3c7ab2de"
BASE = "543316d27720db89ce660dd9cad4c0aa4f5ecadebf77f03685e1ed78bcff5fc0"
F32 = P.project


def rounded(values):
    need(values.dtype == np.dtype("<f4") and np.isfinite(values).all(), "finite float32")
    bits = values.view("<u4")
    # 0x1000 halfway rounds up only for an odd retained significand.
    raw = (bits + np.uint32(0xFFF) + ((bits >> 13) & 1)) & np.uint32(0xFFFFE000)
    result = raw.view("<f4")
    need(np.isfinite(result).all(), "nonfinite result of rounding")
    return result


def parameters(c7, folder, expected):
    extra = json.loads(file(folder / "parameters.json", BUNDLE))
    raw = json.loads(file(c7 / "results" / P.C299 / "raw-manifest.json", P.C299_MANIFEST))["files"]
    loc = {r["path"]: r for r in raw}
    tensors, hashes = [], {}
    read_extra = {}
    for layer in range(P.LAYERS):
        triple = []
        for role, shape in P.ROLES.items():
            name = f"blk.{layer}.{role}"
            f = name + ".f32"
            if 2 <= layer <= 24:
                rel = f"results/{P.C299}/raw/c299-code153-2-estimate.native/{f}"
                meta = loc[rel]
                data = file(c7 / rel, meta["sha256"], meta["size_bytes"])
            else:
                meta = extra[f]
                data = file(folder / "parameters" / f, meta["sha256"], meta["bytes"])
                read_extra[f] = meta
            v = np.frombuffer(data, dtype="<f4").reshape(shape[::-1])
            need(np.isfinite(v).all(), "finite archived parameters")
            triple.append(v)
            hashes[name] = sha(data)
        tensors.append(tuple(triple))
    need(
        read_extra == extra
        and len(extra) == 39
        and sha(json.dumps(hashes, sort_keys=True).encode()) == expected,
        "private and C299 parameters",
    )
    return tensors


def native_mix(part, rows):
    manifest = json.loads(file(part / "manifest.json", P.PART23))["files"]
    root = f"{P.RUN}/raw/{P.RUN}.capture/"

    def member(name):
        key = root + name
        entry = manifest[key]
        return file(part / key, entry["sha256"], entry["bytes"])

    out = {}
    for r in csv.DictReader(member("index.tsv").decode().splitlines(), delimiter="\t"):
        if r["name"] != "ffn_moe_weights_softmax":
            continue
        key = r["phase"], int(r["layer"])
        n = len(rows[key]["ffn_moe_topk"])
        name = r["file"]
        need(
            key not in out
            and Path(name).name == name
            and r["type"] == "f32"
            and int(r["first_abs"]) == rows[key]["start"]
            and r["ne"] == f"1,4,{n},1"
            and r["nb"] == f"4,4,16,{16 * n}"
            and int(r["bytes"]) == 16 * n
            and int(r["state_tokens"]) == n,
            "native mixing weights",
        )
        v = np.frombuffer(member(name), dtype="<f4").reshape(n, 4)
        need(np.isfinite(v).all() and (v >= 0).all() and (v <= 1).all(), "finite mixing range")
        out[key] = v
    need(out.keys() == rows.keys(), "mixture population")
    return out


def native_order_softmax(values, ids):
    selected = np.take_along_axis(values, ids, axis=1)
    e = np.exp(selected - selected.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def surrogate(params):
    # The parent looks up this function for both +0 and the two future projections.
    layers = {id(w): i for i, (_, w, _) in enumerate(params)}
    matrices = {id(w): rounded(w) for i, (_, w, _) in enumerate(params) if i >= 25}

    def project(x, w, b):
        target = layers[id(w)]
        if target >= 25 and len(x) in (29, 32):
            return F32(rounded(x), matrices[id(w)], b)
        return F32(x, w, b)

    return project


def run(a, r):
    need(
        sha((HERE / "protocol.md").read_bytes()) == METHOD
        and sha((HERE.parent / "score.py").read_bytes())
        == "03de669b9edc6d43aae31b690745ebbba3446416f5db87c0c625b50e1e4e068e",
        "frozen methods",
    )
    need(
        all(os.environ.get(k) == "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")),
        "one thread",
    )
    original = json.loads(file(HERE.parent / "receipt.json", BASE))
    rows, _, idx = P.capture(a.part23)
    prior = original["weights"]["weights_sha256"]
    params = parameters(a.c7, a.bundle, prior)
    need(
        idx == original["index_sha256"]
        and P.calibration(rows, params) == original["calibration"]
        and all(np.all(norm != 0) for norm, _, _ in params),
        "reproduce original +0",
    )
    mix = native_mix(a.part23, rows)
    P.project = surrogate(params)
    cal = P.calibration(rows, params)
    bad = []
    comparison = {}
    for (phase, layer), s in rows.items():
        _, w, b = params[layer]
        _, score = P.project(s["attn_post_norm"], w, b)
        real = s["ffn_moe_topk"]
        pred = P.ranks(score)
        for i in np.flatnonzero((pred != real).any(axis=1)):
            native = s["ffn_moe_logits"][i] + b
            order = np.argsort(-native, kind="stable")
            bad.append(
                dict(
                    phase=phase,
                    layer=layer,
                    position=s["start"] + int(i),
                    cols=len(real),
                    predicted_experts_native_rank_1based=[
                        int(np.flatnonzero(order == v)[0]) + 1 for v in pred[i]
                    ],
                )
            )
        c = comparison.setdefault(
            ("prefill" if phase.startswith("prefill") else "decode")
            + "/"
            + ("CPU" if layer < 25 else "CUDA"),
            dict(
                words=0,
                native_reconstruction_different_bits=0,
                projected_different_bits=0,
                native_reconstruction_max_abs=0.0,
                projected_max_abs=0.0,
                native_sum_max_error=0.0,
                projected_sum_max_error=0.0,
            ),
        )
        truth = mix[phase, layer]
        x = native_order_softmax(s["ffn_moe_logits"] + b, real)
        y = native_order_softmax(score, real)
        c["words"] += truth.size
        for name, p in (("native_reconstruction", x), ("projected", y)):
            c[name + "_different_bits"] += int((p.view("<u4") != truth.view("<u4")).sum())
            c[name + "_max_abs"] = max(c[name + "_max_abs"], float(abs(p - truth).max()))
        c["native_sum_max_error"] = max(
            c["native_sum_max_error"], float(abs(truth.sum(axis=1) - 1).max())
        )
        c["projected_sum_max_error"] = max(
            c["projected_sum_max_error"], float(abs(y.sum(axis=1) - 1).max())
        )
    r.update(
        index_sha256=idx,
        weights_sha256=prior,
        private_manifest_sha256=BUNDLE,
        calibration=cal,
        rank_mismatches=bad,
        mix_per_native_rank=comparison,
        gguf_read_bytes=0,
        previous_calibration_reproduced=True,
        numpy_version=np.__version__,
    )
    need(
        sum(c["rows"] for c in cal.values()) == 3400
        and sum(c["words"] for c in comparison.values()) == 13600,
        "coverage",
    )
    if bad or any(
        c["native_reconstruction_max_abs"] > 1e-6 or c["native_sum_max_error"] > 1e-6
        for c in comparison.values()
    ):
        r["status"] = "INCONCLUSIVE_TF32_CALIBRATION"
        return
    result = P.evaluate(rows, params)
    r.update(
        status="MEASURED_TF32_ROUTER_SIGNAL",
        results=result,
        prefill_horizons_above_source_route_both_tiers=[
            h
            for h in (1, 2)
            if all(
                result[f"+{h}/prefill/{tier}"]["paired_extra_hits_vs_source"] > 0
                for tier in ("CPU", "CUDA")
            )
        ],
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("part23", "c7", "bundle", "new-output-dir"):
        cli.add_argument("--" + key, required=True, type=Path)
    args = cli.parse_args()
    os.umask(0o077)
    folder = args.new_output_dir
    folder.mkdir()
    rec = dict(
        status="FAIL_PRESERVED",
        method_sha256=METHOD,
        program_sha256=sha(Path(__file__).read_bytes()),
    )
    try:
        run(args, rec)
    except Exception as e:
        rec.update(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    txt = (json.dumps(rec, sort_keys=True, indent=2) + "\n").encode()
    need(len(txt) <= 2 << 20, "output limit")
    (folder / "receipt.json").write_bytes(txt)
    print(rec["status"], rec.get("reason", ""))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))
