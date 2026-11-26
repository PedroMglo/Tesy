"""Compare proposals at equal issued volume with the archived target's previous tile."""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
M = run_path(HERE / "score.py")
P, TF, need = M["P"], M["TF"], M["need"]
METHOD = "ea3a1c46957661b55f62683aefef49f5a78e749362f1d98f2cdc555e2bffa3b7"
ORIGIN = "5e83418c00905348b46a442f0caee4affbf7ab3073a3faaeff8f958971e02c05"


def compare(a, b, eligible):
    k = min(len(a), len(b))
    need(k <= 4 and len(set(a)) == len(a) and len(set(b)) == len(b), "distinct proposals")
    hits_a, hits_b = (len(set(ids[:k]) & eligible) for ids in (a, b))
    return Counter(
        sites=1,
        each_issues=k,
        projection_hits=hits_a,
        recency_hits=hits_b,
        projection_wins=int(hits_a > hits_b),
        recency_wins=int(hits_b > hits_a),
        ties=int(hits_a == hits_b),
        zero_issues=int(k == 0),
    )


def run(args):
    P.file(HERE / "equal-issues.md", METHOD)
    prog = "6a842b9c9036d0c659db9262df5175f2e43793a29de0cd25bd894bb1f66eea9b"
    P.file(HERE / "score.py", prog)
    origin = json.loads(P.file(args.original / "receipt.json", ORIGIN))
    check = dict(status="FAIL_PRESERVED", method_sha256=M["METHOD"], program_sha256=prog)
    M["run"](args, check)
    need(check == origin, "all original cells independently regenerated")
    rows, _, _ = P.capture(args.part23)
    calibrated = json.loads(P.file(HERE.parent / "tf32/receipt.json", M["CAL"]))
    params = TF["parameters"](args.c7, args.bundle, calibrated["weights_sha256"])
    P.project = TF["surrogate"](params)
    path = args.part95 / "tesy-c292-pack-numeric-physical-20261125-r02/overlay_on/raw/phase.pfj1"
    events, hdr = M["AUDIT"]["read_journal"](path)
    need(hdr == origin["journal"], "journal reread")
    tiles, _, _, cuts, routes, demands, bysite = M["journal"](events)
    predecessor = dict(zip(list(tiles)[1:], list(tiles)[:-1], strict=True))
    positions = {bounds[0]: tile for tile, bounds in tiles.items()}
    counts, old = defaultdict(Counter), defaultdict(Counter)
    for (phase, layer), gold in rows.items():
        tile = positions[P.PHASES[phase][0]]
        if not layer or tile not in predecessor:
            continue
        site = (*tile, layer)
        prior = routes.get((*predecessor[tile], layer))
        if not prior:
            continue
        src = rows[phase, layer - 1]
        index = gold["start"] - src["start"]
        n = len(gold["ffn_moe_topk"])
        pred = P.infer(
            src["attn_post_norm"][index : index + n], params[layer - 1][0], params[layer]
        )
        cut, _, occupied = cuts[site]
        requested = set(demands[site])
        missing = {
            key[-1]
            for index, key, _, _ in bysite[site]
            if index > cut and key in requested and key[-1] not in occupied
        }
        a, b = (M["choose"](r, occupied, 4)[0] for r in (pred, prior))
        group = ("prefill" if phase.startswith("prefill") else "decode") + (
            "/CPU" if layer < 25 else "/CUDA"
        )
        counts[group].update(compare(a, b, missing))
        for name, ids in (("projection_paired", a), ("previous_target", b)):
            old[f"{group}/{name}/four"].update(
                offers=len(ids), jobs_hit=len(set(ids) & missing), sites=1
            )
    for label, cell in old.items():
        need(
            all(origin["counts"][label][k] == v for k, v in cell.items()), "common-cap reproduction"
        )
    need(len(counts) == 4 and len(old) == 8, "both tiers and phases")
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("part23", "part95", "c7", "bundle", "original", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    rec = dict(
        status="FAIL_PRESERVED",
        original_sha256=ORIGIN,
        method_sha256=METHOD,
        program_sha256=P.sha(Path(__file__).read_bytes()),
    )
    try:
        cells = run(args)
        result = all(
            cells["prefill/" + tier]["projection_hits"] > cells["prefill/" + tier]["recency_hits"]
            for tier in ("CPU", "CUDA")
        )
        rec.update(
            status="BETTER_ON_EQUAL_ISSUES" if result else "INCONCLUSIVE_EQUAL_ISSUES", counts=cells
        )
    except Exception as e:
        rec.update(reason=f"{type(e).__name__}: {e}")
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(rec, f, indent=2, sort_keys=True)
        f.write("\n")
    print(rec["status"], rec.get("reason", ""))
    raise SystemExit(int(rec["status"] == "FAIL_PRESERVED"))
