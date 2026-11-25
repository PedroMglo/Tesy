"""Compare one fixed cross-layer router signal against authenticated C270 ranks."""

import argparse
import csv
import hashlib
import json
import os
import re
import stat
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROTOCOL = "89094398518ceef7185a14c9457b0b6fb6c3526c0d1836ae3d0fb82d44965a9c"
PART23 = "d79d180a18cf6c0f0767d02307904e679c0edd4fa10c12a3256b87a398dd8002"
C299 = "c299-true-routing-score-alias-repair-20261006"
C299_MANIFEST = "3b270b0d010f64ad53c3aa4e968a81a22e144ffaa785fc888b9338d788b5f240"
META = "2c8ca725f50000bf3177712cfa30d29a809f77f25826b425ea67d8fcbffd6d82"
PLACE = "50a35a1e5c3fde78066d1378e13dfeb89867d9970528135ff3294c6aa5bd1bf7"
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
RUN = "tesy-c270-driver-20261125-r01"
LAYERS, WIDTH, EXPERTS = 36, 2880, 128
PHASES = {
    "prefill0": (0, 32),
    "prefill128": (128, 32),
    "prefill_final": (160, 29),
    "decode0": (189, 1),
    "decode1": (190, 1),
    "decode7": (196, 1),
    "decode31": (220, 1),
}
ROLES = {
    "post_attention_norm.weight": (WIDTH,),
    "ffn_gate_inp.weight": (WIDTH, EXPERTS),
    "ffn_gate_inp.bias": (EXPERTS,),
}
STAGES = {
    "attn_post_norm": (WIDTH, "f32"),
    "ffn_moe_logits": (EXPERTS, "f32"),
    "ffn_moe_topk": (4, "i32"),
}


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file(path, digest, length=None):
    info = path.lstat()
    need(
        stat.S_ISREG(info.st_mode)
        and info.st_size < 16 << 20
        and (length is None or length == info.st_size),
        "file bounds: " + path.name,
    )
    data = path.read_bytes()
    need(sha(data) == digest, "digest: " + path.name)
    return data


def identity(info):
    return dict(
        dev=info.st_dev,
        inode=info.st_ino,
        size_bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
    )


def weights(args, expected_stat):
    m = json.loads(file(args.c7 / "results" / C299 / "raw-manifest.json", C299_MANIFEST))["files"]
    original = {x["path"]: x for x in m}
    md = [
        json.loads(line)
        for line in file(
            args.c7
            / "results/c283-exact-expert-service-epoch-20261006T194311Z"
            / "build/model-tensor-metadata.jsonl",
            META,
        ).splitlines()
    ]
    hdr, *entries = md
    index = {x["name"]: x for x in entries}
    need(
        len(index) == len(entries) == hdr["tensor_count"] == 687 and hdr["gguf_version"] == 3,
        "inventory",
    )
    place = json.loads(file(args.placement, PLACE))
    path = Path(place["working_copy"])
    need(
        place["status"] == "PASS_NVME_MODEL_PLACEMENT"
        and place["source_sha256"] == place["destination_direct_reread"]["sha256"] == MODEL
        and path.resolve(strict=True) == path
        and path.samefile(place["launcher_path"])
        and place["destination_transport"] == "nvme",
        "placement",
    )
    result, hashes = [], {}
    nreads = nbytes = 0
    with os.fdopen(
        os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW), "rb", buffering=0
    ) as stream:
        fd = stream.fileno()
        initial = identity(os.fstat(fd))
        need(
            initial == expected_stat == identity(path.stat())
            and stat.S_ISREG(os.fstat(fd).st_mode)
            and initial["size_bytes"] == place["source_size"] == 63_387_346_208,
            "FD identity",
        )
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
        for layer in range(LAYERS):
            params = []
            for role, shape in ROLES.items():
                name = f"blk.{layer}.{role}"
                t = index[name]
                size = 4 * int(np.prod(shape))
                off = t["data_offset"]
                need(
                    t["tensor_type"] == "f32"
                    and t["shape"] == list(shape)
                    and t["n_bytes"] == size
                    and off == hdr["data_offset"] + t["relative_data_offset"]
                    and off % hdr["alignment"] == 0
                    and 0 <= off <= initial["size_bytes"] - size,
                    "tensor descriptor",
                )
                if 2 <= layer <= 24:
                    rel = f"results/{C299}/raw/c299-code153-2-estimate.native/{name}.f32"
                    data = file(args.c7 / rel, original[rel]["sha256"], original[rel]["size_bytes"])
                else:
                    need(nbytes + size <= 19_325_696, "additional GGUF byte cap")
                    data = os.pread(fd, size, off)
                    nreads += 1
                    nbytes += len(data)
                need(len(data) == size, "router range")
                v = np.frombuffer(data, dtype="<f4").reshape(shape[::-1])
                need(np.isfinite(v).all(), "finite parameters")
                params.append(v)
                hashes[name] = sha(data)
            result.append(tuple(params))
        need(
            identity(os.fstat(fd)) == identity(path.stat()) == initial
            and nreads == 39
            and nbytes == 19_325_696,
            "weight conservation",
        )
    return result, dict(
        archived_components=69,
        gguf_reads=nreads,
        gguf_returned_bytes=nbytes,
        weights_sha256=sha(json.dumps(hashes, sort_keys=True).encode()),
        model_sha256=MODEL,
    )


def matrix(raw, row, n, dtype):
    ne = tuple(map(int, row["ne"].split(",")))
    nb = tuple(map(int, row["nb"].split(",")))
    count = int(row["state_tokens"])
    pitch = 512 if dtype == "i32" else 4 * n
    need(
        ne == (n, count, 1, 1)
        and nb == (4, pitch, count * pitch, count * pitch)
        and row["type"] == dtype
        and len(raw) == int(row["bytes"]) == (count - 1) * pitch + 4 * n,
        "shape, length or stride",
    )
    return np.ndarray(
        (count, n), buffer=raw, dtype="<i4" if dtype == "i32" else "<f4", strides=(pitch, 4)
    ).copy()


def capture(part):
    manifest = json.loads(file(part / "manifest.json", PART23))["files"]

    def member(rel):
        item = manifest[rel]
        return file(part / rel, item["sha256"], item["bytes"])

    base = f"{RUN}/raw/{RUN}.capture/"
    stderr = member(f"{RUN}/raw/{RUN}.stderr").decode()
    tiers = dict(
        (int(layer), v)
        for layer, v in re.findall(
            r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0),", stderr
        )
    )
    need(
        all(tiers.get(layer) == ("CPU" if layer < 25 else "CUDA0") for layer in range(LAYERS)),
        "placement of layers",
    )
    index = member(base + "index.tsv")
    rows = {}
    for r in csv.DictReader(index.decode().splitlines(), delimiter="\t"):
        stage = r["name"]
        if stage not in STAGES:
            continue
        phase = r["phase"]
        layer = int(r["layer"])
        p = int(r["first_abs"])
        need(phase in PHASES and 0 <= layer < LAYERS, "capture population")
        start, count = PHASES[phase]
        if layer == 35 and phase.startswith("prefill"):
            need(phase == "prefill_final", "pruned layer")
            start, count = 188, 1
        name = r["file"]
        need(
            Path(name).name == name and start == p and count == int(r["state_tokens"]),
            "member identity",
        )
        key = phase, layer
        store = rows.setdefault(key, {})
        need(stage not in store, "duplicate cut")
        v = matrix(member(base + name), r, *STAGES[stage])
        if stage == "ffn_moe_topk":
            need(
                ((0 <= v) & (v < EXPERTS)).all()
                and (np.diff(np.sort(v, axis=1), axis=1) > 0).all(),
                "four valid experts",
            )
        else:
            need(np.isfinite(v).all(), "finite row")
        store[stage] = v
        store["start"] = start
    needed = {
        (phase, layer)
        for phase in PHASES
        for layer in range(LAYERS)
        if not (layer == 35 and phase in ("prefill0", "prefill128"))
    }
    need(
        set(rows) == needed and all(set(s) == set(STAGES) | {"start"} for s in rows.values()),
        "full capture population",
    )
    return rows, json.loads(member(f"{RUN}/protocol.json"))["model_stat"], sha(index)


def ranks(scores):
    need(np.isfinite(scores).all(), "finite scores")
    return np.argsort(-scores, axis=1, kind="stable")[:, :4]


def project(x, w, b):
    need(
        x.ndim == w.ndim == 2 and x.shape[1] == w.shape[1] and b.shape == (w.shape[0],), "gate axis"
    )
    raw = x @ w.T
    return raw, raw + b


def infer(x, source_gamma, dest):
    n, w, b = dest
    need(np.all(source_gamma != 0), "zero source gamma")
    return ranks(project((x / source_gamma) * n, w, b)[1])


def metrics():
    return {"rows": 0, "hits_hist": [0] * 5, "hits": 0, "set_exact": 0, "ordered_exact": 0}


def count(m, pred, gold):
    n = len(gold)
    need(pred.shape == gold.shape == (n, 4), "paired ranks")
    hits = (pred[:, :, None] == gold[:, None, :]).any(axis=2).sum(axis=1)
    for h in range(5):
        m["hits_hist"][h] += int((hits == h).sum())
    m["hits"] += int(hits.sum())
    m["rows"] += n
    m["set_exact"] += int((hits == 4).sum())
    m["ordered_exact"] += int((pred == gold).all(axis=1).sum())


def previous(routed, t, p, phase):
    last = routed.get((t, p - 1))
    return last[1] if last and last[0] != phase else None


def calibration(rows, params):
    checks = {}
    for (phase, layer), s in rows.items():
        name = (
            ("prefill" if phase.startswith("prefill") else "decode")
            + "/"
            + ("CPU" if layer < 25 else "CUDA")
        )
        c = checks.setdefault(
            name,
            dict(
                rows=0,
                projected_order_misses=0,
                archived_order_misses=0,
                logits_words=0,
                different_logit_bits=0,
                max_abs=0.0,
                min_4th_minus_5th=None,
            ),
        )
        _, w, b = params[layer]
        calc, scores = project(s["attn_post_norm"], w, b)
        before = s["ffn_moe_logits"]
        gold = s["ffn_moe_topk"]
        c["rows"] += len(gold)
        c["projected_order_misses"] += int(((ranks(scores) != gold).any(axis=1)).sum())
        c["archived_order_misses"] += int(((ranks(before + b) != gold).any(axis=1)).sum())
        c["logits_words"] += before.size
        c["different_logit_bits"] += int((calc.view("<u4") != before.view("<u4")).sum())
        c["max_abs"] = max(c["max_abs"], float(abs(calc - before).max()))
        sort = np.sort(before + b, axis=1)
        gap = float((sort[:, -4] - sort[:, -5]).min())
        c["min_4th_minus_5th"] = (
            gap if c["min_4th_minus_5th"] is None else min(gap, c["min_4th_minus_5th"])
        )
    return checks


def evaluate(rows, params):
    routed = {
        (layer, s["start"] + i): (phase, v)
        for (phase, layer), s in rows.items()
        for i, v in enumerate(s["ffn_moe_topk"])
    }
    out = {}
    for h in (1, 2):
        for (phase, t), s in sorted(rows.items()):
            src = rows.get((phase, t - h))
            if not src:
                continue
            idx = s["start"] - src["start"]
            gold = s["ffn_moe_topk"]
            n = len(gold)
            need(0 <= idx <= len(src["ffn_moe_topk"]) - n, "shared absolute positions")
            pred = infer(src["attn_post_norm"][idx : idx + n], params[t - h][0], params[t])
            adjacent = src["ffn_moe_topk"][idx : idx + n]
            cell = (
                f"+{h}/"
                + ("prefill" if phase.startswith("prefill") else "decode")
                + "/"
                + ("CPU" if t < 25 else "CUDA")
            )
            group = out.setdefault(
                cell,
                {
                    k: metrics()
                    for k in (
                        "projection",
                        "source_route",
                        "recency",
                        "projection_on_recency_rows",
                        "source_route_on_recency_rows",
                    )
                },
            )
            count(group["projection"], pred, gold)
            count(group["source_route"], adjacent, gold)
            for i in range(n):
                prev = previous(routed, t, s["start"] + i, phase)
                if prev is not None:
                    count(group["recency"], prev[None, :], gold[i : i + 1])
                    count(group["projection_on_recency_rows"], pred[i : i + 1], gold[i : i + 1])
                    count(
                        group["source_route_on_recency_rows"], adjacent[i : i + 1], gold[i : i + 1]
                    )
    for group in out.values():
        for m in group.values():
            m["recall"] = m["hits"] / (4 * m["rows"]) if m["rows"] else None
        group["paired_extra_hits_vs_source"] = (
            group["projection"]["hits"] - group["source_route"]["hits"]
        )
        group["paired_extra_hits_vs_recency"] = (
            group["projection_on_recency_rows"]["hits"] - group["recency"]["hits"]
        )
    return out


def run(a, r):
    need(sha((HERE / "protocol.md").read_bytes()) == PROTOCOL, "protocol")
    need(
        all(os.environ.get(k) == "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")),
        "one thread",
    )
    rows, identity_, idx_sha = capture(a.part23)
    params, summary = weights(a, identity_)
    c = calibration(rows, params)
    r.update(
        weights=summary,
        calibration=c,
        index_sha256=idx_sha,
        phase_rows={
            p: sum(len(s["ffn_moe_topk"]) for (n, _), s in rows.items() if n == p) for p in PHASES
        },
        zero_gammas=sum(int((p[0] == 0).sum()) for p in params),
        numpy_version=np.__version__,
    )
    if (
        any(v["projected_order_misses"] or v["archived_order_misses"] for v in c.values())
        or r["zero_gammas"]
    ):
        r["status"] = "INCONCLUSIVE_CALIBRATION_OR_GAMMA"
        return
    out = evaluate(rows, params)
    horizons = [
        h
        for h in (1, 2)
        if all(
            out[f"+{h}/prefill/{tier}"]["paired_extra_hits_vs_source"] > 0
            for tier in ("CPU", "CUDA")
        )
    ]
    r.update(
        status="MEASURED_FEATURE_SIGNAL_ONLY",
        prefill_horizons_above_source_route_both_tiers=horizons,
        results=out,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("part23", "c7", "placement", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    r = {
        "status": "FAIL_PRESERVED",
        "protocol_sha256": PROTOCOL,
        "program_sha256": sha(Path(__file__).read_bytes()),
    }
    try:
        run(a, r)
    except Exception as e:
        r["status"] = "FAIL_PRESERVED"
        r["reason"] = f"{type(e).__name__}: {e}"
    output = (json.dumps(r, sort_keys=True, indent=2) + "\n").encode()
    need(len(output) <= 2 << 20, "public output cap")
    (a.new_output_dir / "receipt.json").write_bytes(output)
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
